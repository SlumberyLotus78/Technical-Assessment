"""Preparación y resultados DQ durables antes de modificar las capas publicadas."""

from datetime import date
from pathlib import Path
from uuid import UUID

import psycopg

from grain_pipeline.common.dates import month_end, months_between
from grain_pipeline.persistence.captures import read_registered_capture
from grain_pipeline.persistence.quality import record_profile_checks, record_quality_result
from grain_pipeline.quality.calendar import check_fix_coverage
from grain_pipeline.quality.profiling import profile_observations
from grain_pipeline.quality.publication import check_combined_observations, validate_capture_set
from grain_pipeline.sources.catalog import get_series
from grain_pipeline.sources.contracts import read_metadata_range
from grain_pipeline.sources.observations import read_observations
from grain_pipeline.transformations.gold import build_monthly_gold
from grain_pipeline.transformations.silver import prepare_observations


def prepare_registered_inputs(connection: psycopg.Connection, run_id: UUID, capture_ids: list[UUID],
                               bronze_root: Path, run: dict, *, as_of: date) -> dict:
    """Reúne fragmentos, certifica la ventana nueva y conserva sus comprobaciones."""
    if not capture_ids or len(set(capture_ids)) != len(capture_ids):
        raise ValueError("Se requieren identificadores de captura únicos.")
    start, end = run["start_month"], run["end_month"]
    captures = []
    for capture_id in capture_ids:
        try:
            capture = read_registered_capture(connection, capture_id, bronze_root)
        except (ValueError, OSError):
            record_quality_result(connection, run_id, rule_code="LIN-01", status="failed",
                                  details={"capture_id": str(capture_id)},
                                  period_start=start, period_end=month_end(end))
            raise
        capture["capture_id"] = capture_id
        captures.append(capture)
        record_quality_result(connection, run_id, rule_code="LIN-01", status="passed",
                              details={"capture_id": str(capture_id), "sha256": capture["content_sha256"]},
                              period_start=start, period_end=month_end(end),
                              provider=capture["provider"], series_code=capture["series_code"])
    try:
        groups = validate_capture_set(captures, run)
    except ValueError:
        record_quality_result(connection, run_id, rule_code="SRC-02", status="failed",
                              details={"reason": "incompatible_capture_set_or_metadata"},
                              period_start=start, period_end=month_end(end))
        raise
    for provider, code in groups["metadata"]:
        for rule in ("SRC-01", "SRC-02"):
            record_quality_result(connection, run_id, rule_code=rule, status="passed", details={},
                                  period_start=start, period_end=month_end(end), provider=provider, series_code=code)

    prepared, observation_ids = [], []
    for capture in groups["observations"]:
        series = get_series(capture["provider"], capture["series_code"])
        try:
            native = read_observations(capture["payload"], series)
            profile = profile_observations(native, series, capture["window_start"], capture["window_end"])
        except ValueError:
            record_quality_result(connection, run_id, rule_code="SRC-03", status="failed",
                                  details={"capture_id": str(capture["capture_id"])},
                                  period_start=capture["window_start"], period_end=capture["window_end"],
                                  provider=series["provider"], series_code=series["code"])
            raise
        record_profile_checks(connection, run_id, capture["capture_id"], profile,
                              include_calendar_placeholder=False)
        rows = prepare_observations(native, series, capture["window_start"], capture["window_end"])
        metadata = groups["metadata"][(series["provider"], series["code"])]
        available_start, available_end = read_metadata_range(metadata, series)
        if any(not available_start <= row["observation_date"] <= available_end for row in rows):
            record_quality_result(connection, run_id, rule_code="SRC-02", status="failed",
                                  details={"capture_id": str(capture["capture_id"]), "reason": "outside_declared_availability"},
                                  period_start=start, period_end=month_end(end),
                                  provider=series["provider"], series_code=series["code"])
            raise ValueError("Una observación queda fuera de la disponibilidad declarada en metadatos.")
        prepared.extend(rows)
        observation_ids.append(capture["capture_id"])

    checks = check_combined_observations(prepared, start, end)
    for check in checks:
        record_quality_result(connection, run_id, rule_code=check["rule_code"], status=check["status"],
                              details=check["details"], period_start=start, period_end=month_end(end))
    for month in months_between(start, end):
        daily = [row for row in prepared if row["provider"] == "Banxico"
                 and row["observation_date"].replace(day=1) == month]
        check = check_fix_coverage(daily, month)
        checks.append(check)
        record_quality_result(connection, run_id, rule_code=check["rule_code"], status=check["status"],
                              details=check["details"], period_start=month, period_end=month_end(month),
                              provider="Banxico", series_code="SF43718")
    if any(check["status"] != "passed" for check in checks):
        raise ValueError("El conjunto requerido tiene reglas de cobertura o duplicados fallidas o pendientes.")
    # El intervalo recibido debe ser completo por sí mismo: Silver previo no puede ocultar omisiones de la nueva respuesta de una fuente.
    build_monthly_gold(prepared, start, end, as_of=as_of)
    record_quality_result(connection, run_id, rule_code="PUB-01", status="passed",
                          details={"scope": "incoming_interval", "observations": len(prepared)},
                          period_start=start, period_end=month_end(end))
    return {"observations": prepared, "observation_ids": observation_ids}
