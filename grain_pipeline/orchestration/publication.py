"""Publicación atómica sobre capturas ya registradas; sin consultas nuevas a APIs."""

from datetime import date
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.pq import TransactionStatus

from grain_pipeline.common.dates import month_end
from grain_pipeline.orchestration.locking import product_publication_lock
from grain_pipeline.orchestration.preparation import prepare_registered_inputs
from grain_pipeline.persistence.catalog import verify_catalog
from grain_pipeline.persistence.gold import read_monthly_gold, read_silver_observations, save_monthly_gold
from grain_pipeline.persistence.observations import save_capture_observations
from grain_pipeline.persistence.quality import record_quality_result
from grain_pipeline.persistence.runs import fail_run, require_running_run, set_run_stage
from grain_pipeline.persistence.schema import verify_schema
from grain_pipeline.persistence.watermarks import complete_publication, read_watermark
from grain_pipeline.quality.publication import (
    merge_observations, observation_values, plan_publication, validate_stored_gold,
)
from grain_pipeline.transformations.gold import build_monthly_gold


def publish_registered_captures(connection: psycopg.Connection, run_id: UUID, capture_ids: list[UUID],
                                bronze_root: Path, *, as_of: date) -> dict:
    """Posee los commits de esta fase, requiere intento y capturas confirmados previamente."""
    with product_publication_lock(connection):
        # Verificar el intento fuera del manejador evita cerrar de nuevo un intento que ya terminó cuando se repite la llamada con el mismo ID.
        try:
            run = require_running_run(connection, run_id)
        except Exception:
            connection.rollback()
            raise
        if run["stage"] not in {"planning", "extraction", "quality"}:
            connection.rollback()
            raise ValueError("La publicación requiere un intento previo a la escritura Silver.")
        stage = "planning"
        try:
            verify_schema(connection)
            verify_catalog(connection)
            previous = read_watermark(connection)
            plan = plan_publication(run, previous, as_of=as_of)
            start, end = plan["start_month"], plan["end_month"]
            record_quality_result(connection, run_id, rule_code="CTL-01", status="passed",
                                  details={"load_type": run["load_type"], "initialized": previous is not None},
                                  period_start=run["start_month"], period_end=month_end(run["end_month"]))
            stage = "quality"
            set_run_stage(connection, run_id, stage)
            inputs = prepare_registered_inputs(connection, run_id, capture_ids, bronze_root, run, as_of=as_of)
            current = read_silver_observations(connection, start, end, bronze_root)
            if previous is not None:
                baseline_end = previous["published_through_month"]
                baseline = [row for row in current if row["observation_date"] <= month_end(baseline_end)]
                baseline_gold = build_monthly_gold(baseline, start, baseline_end, as_of=as_of)
                validate_stored_gold(baseline_gold, read_monthly_gold(connection, start, baseline_end))
            combined = merge_observations(current, inputs["observations"])
            expected = build_monthly_gold(combined, start, end, as_of=as_of)
            record_quality_result(connection, run_id, rule_code="PUB-02", status="passed",
                                  details={"scope": "complete_publication_interval", "grain_references": len(expected["grain_reference_monthly"])},
                                  period_start=start, period_end=month_end(end))
            # Primer límite: se conserva el diagnóstico sin modificar hechos,
            # Gold ni watermark. El bloqueo de sesión permanece adquirido.
            connection.commit()

            stage = "silver"
            set_run_stage(connection, run_id, stage)
            silver_metrics = []
            for capture_id in inputs["observation_ids"]:
                silver_metrics.append(save_capture_observations(connection, run_id, capture_id, bronze_root))
            stored_silver = read_silver_observations(connection, start, end, bronze_root)
            if observation_values(stored_silver) != observation_values(combined):
                raise ValueError("Silver cambió respecto del conjunto preparado para publicar.")
            stage = "gold"
            set_run_stage(connection, run_id, stage)
            written = save_monthly_gold(connection, run_id, start, end, bronze_root, as_of=as_of)
            validate_stored_gold(expected, read_monthly_gold(connection, start, end))
            stage = "publication"
            set_run_stage(connection, run_id, stage)
            for code in ("PUB-03", "PUB-04", "CTL-02", "CTL-03", "CTL-04"):
                record_quality_result(connection, run_id, rule_code=code, status="passed",
                                      details={"scope": "complete_publication_interval"},
                                      period_start=start, period_end=month_end(end))
            complete_publication(connection, run_id, previous, plan, bronze_root, as_of=as_of)
            # Segundo límite: Silver, Gold, avance y éxito quedan visibles juntos.
            connection.commit()
            return {"run_id": str(run_id), "start_month": start.isoformat(), "end_month": end.isoformat(),
                    "silver": {field: sum(metrics[field] for metrics in silver_metrics)
                               for field in ("received", "written", "unchanged")},
                    "gold": written["metrics"]}
        except Exception as error:
            if connection.closed or connection.broken:
                # Sin conexión no se puede confirmar el diagnóstico. La
                # recuperación deberá consultar el estado durable del intento.
                raise
            # Una transacción SQL fallida debe revertirse antes de escribir su
            # diagnóstico. Los controles previos ya confirmados se conservan.
            if stage in {"planning", "quality"} and connection.info.transaction_status == TransactionStatus.INTRANS:
                # Una regla Python fallida no invalida la transacción SQL.
                # Esta fase solo escribió logs, que deben conservarse.
                connection.commit()
            else:
                connection.rollback()
            code = "CTL-01" if stage == "planning" else "PUB-01" if stage == "quality" else "CTL-03"
            if run["start_month"] is not None:
                record_quality_result(connection, run_id, rule_code=code, status="failed",
                                      details={"stage": stage, "error_type": type(error).__name__},
                                      period_start=run["start_month"], period_end=month_end(run["end_month"]))
            fail_run(connection, run_id, stage, error)
            connection.commit()
            raise
