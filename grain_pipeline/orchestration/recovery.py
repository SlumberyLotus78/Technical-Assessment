"""Recuperación explícita sin APIs: intento nuevo, capturas originales y publicación común."""

import argparse
from datetime import date, datetime
from pathlib import Path
import sys
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg

from grain_pipeline.common.config import load_database_url
from grain_pipeline.common.dates import OPERATING_TIMEZONE, month_end
from grain_pipeline.extraction.raw import write_json
from grain_pipeline.orchestration.artifacts import write_capture_manifest, write_run_result, write_window_profile
from grain_pipeline.orchestration.failures import record_attempt_failure
from grain_pipeline.orchestration.locking import product_publication_lock
from grain_pipeline.orchestration.publication import publish_registered_captures
from grain_pipeline.persistence.catalog import verify_catalog
from grain_pipeline.persistence.database import database_error_message, open_connection
from grain_pipeline.persistence.quality import record_quality_result
from grain_pipeline.persistence.recovery import (
    close_abandoned_attempt, has_newer_publication, read_attempt, read_attempt_captures, read_successful_recovery,
)
from grain_pipeline.persistence.runs import begin_run, set_run_stage
from grain_pipeline.persistence.schema import verify_schema
from grain_pipeline.persistence.watermarks import read_watermark
from grain_pipeline.quality.publication import plan_publication
from grain_pipeline.quality.recovery import recovery_decision


def retry_instruction(attempt: dict, watermark: dict | None) -> str:
    """Explica el reintento seguro cuando los originales no permiten una recuperación."""
    first, last = attempt["start_month"], attempt["end_month"]
    if watermark is None:
        if first is None:
            return "historical --start-month YYYY-MM --end-month YYYY-MM"
        return f"historical --start-month {first:%Y-%m} --end-month {last:%Y-%m}"
    if (watermark is not None and first is not None and first >= watermark["start_month"]
            and last <= watermark["published_through_month"]):
        return f"reprocess --start-month {first:%Y-%m} --end-month {last:%Y-%m}"
    return "incremental"


def recover_run(connection: psycopg.Connection, source_id: UUID, bronze_root: Path, *, as_of: date) -> dict:
    """Cierra un huérfano bajo bloqueo; jamás vuelve a abrir su fila para escribir datos."""
    with product_publication_lock(connection):
        verify_schema(connection)
        verify_catalog(connection)
        source = read_attempt(connection, source_id)
        completed = read_successful_recovery(connection, source_id)
        if completed is not None or source["status"] in {"succeeded", "skipped"}:
            connection.commit()
            return {"action": "already_completed", "source_run_id": str(source_id),
                    "run_id": str(completed or source_id)}
        previous = read_watermark(connection)
        records = read_attempt_captures(connection, source_id)
        decision = recovery_decision(source, records, newer_publication=has_newer_publication(connection, source))
        close_abandoned_attempt(connection, source, decision)
        connection.commit()  # El diagnóstico del huérfano sobrevive a un fallo posterior.
        if decision["action"] != "reuse_captures":
            return {**decision, "source_run_id": str(source_id), "retry": retry_instruction(source, previous)}
        # La misma regla de continuidad del publicador también protege la recuperación.
        plan_publication(source, previous, as_of=as_of)
        run_id = begin_run(connection, source["load_type"], source["start_month"], source["end_month"])
        capture_ids = [row["capture_id"] for row in records]
        record_quality_result(connection, run_id, rule_code="CTL-05", status="passed",
                              details={"operation": "recovery", "source_run_id": str(source_id),
                                       "capture_ids": [str(value) for value in capture_ids]},
                              period_start=source["start_month"], period_end=month_end(source["end_month"]))
        connection.commit()
        directory = bronze_root / "recovery" / str(run_id)
        stage = "planning"
        try:
            directory.mkdir(parents=True)
            write_json(directory / "query_plan.json", {"operation": "recovery", "run_id": str(run_id),
                       "source_run_id": str(source_id), "api_requests": 0,
                       "start_month": source["start_month"].isoformat(), "end_month": source["end_month"].isoformat()})
            stage = "quality"
            set_run_stage(connection, run_id, stage)
            captures = write_capture_manifest(connection, run_id, capture_ids, bronze_root, directory)
            write_window_profile(run_id, captures, source["start_month"], source["end_month"], directory, "incoming_profile.json")
            result = publish_registered_captures(connection, run_id, capture_ids, bronze_root, as_of=as_of)
        except Exception as error:
            record_attempt_failure(connection, run_id, stage, "quality", error,
                                   start=source["start_month"], end=source["end_month"])
            raise
        result.update(action="recovered", status="succeeded", source_run_id=str(source_id),
                      bronze_directory=directory.relative_to(bronze_root).as_posix())
        write_run_result(directory, result, filename="run_result.json")
        return result


def main(argv=None) -> int:
    """No necesita llaves de APIs; las respuestas se reutilizan solo después de verificarlas."""
    parser = argparse.ArgumentParser(description="Recupera un intento completo o indica el reintento necesario.")
    parser.add_argument("--run-id", required=True, type=UUID)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--bronze-root", type=Path, default=Path("data/bronze"))
    args = parser.parse_args(argv)
    try:
        as_of = datetime.now(ZoneInfo(OPERATING_TIMEZONE)).date()
        with open_connection(load_database_url(args.env_file)) as connection:
            result = recover_run(connection, args.run_id, args.bronze_root, as_of=as_of)
    except ZoneInfoNotFoundError:
        print("Faltan datos de zona horaria; instala requirements.txt.", file=sys.stderr)
        return 1
    except psycopg.Error as error:
        print(database_error_message(error), file=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except OSError:
        print("No se pudo comprobar la configuración o las capturas locales.", file=sys.stderr)
        return 1
    print(f"Recuperación | origen: {result['source_run_id']} | decisión: {result['action']}")
    if result["action"] == "retry_required":
        print(f"Motivo: {result['reason']} | ejecutar: python -m grain_pipeline.orchestration.{result['retry']} --env-file {args.env_file}")
        return 2
    print(f"Ejecución confirmada: {result['run_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
