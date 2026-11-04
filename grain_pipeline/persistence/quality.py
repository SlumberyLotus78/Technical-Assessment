"""Persistencia de resultados DQ, la decisión de cada regla pertenece a quality."""

from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from grain_pipeline.common.dates import parse_date
from grain_pipeline.persistence.captures import read_registered_capture
from grain_pipeline.persistence.runs import require_running_run
from grain_pipeline.quality.observations import profile_checks
from grain_pipeline.quality.profiling import profile_observations
from grain_pipeline.sources.catalog import get_series
from grain_pipeline.sources.observations import read_observations


def record_quality_result(connection: psycopg.Connection, run_id: UUID, *, rule_code: str,
                          status: str, details: dict, period_start: date, period_end: date,
                          provider: str | None = None, series_code: str | None = None) -> UUID:
    """Registra una evaluación, cada llamada conserva su propio identificador."""
    require_running_run(connection, run_id)
    if status not in {"passed", "failed", "pending"} or not isinstance(details, dict):
        raise ValueError("Resultado DQ incompatible.")
    result_id = uuid4()
    connection.execute(
        """INSERT INTO ops.dq_results
           (dq_result_id, run_id, rule_code, provider, series_code, period_start, period_end, status, details)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (result_id, run_id, rule_code, provider, series_code, period_start, period_end, status, Jsonb(details)))
    return result_id


def record_capture_profile(connection: psycopg.Connection, run_id: UUID,
                           capture_id: UUID, bronze_root: Path) -> dict:
    """Recalcula el perfil desde la captura íntegra y registra sus reglas aplicables."""
    require_running_run(connection, run_id)
    capture = read_registered_capture(connection, capture_id, bronze_root)
    if capture["kind"] != "observations":
        raise ValueError("El perfil requiere una captura de observaciones.")
    series = get_series(capture["provider"], capture["series_code"])
    start, end = capture["window_start"], capture["window_end"]
    records = read_observations(capture["payload"], series)
    profile = profile_observations(records, series, start, end)
    record_profile_checks(connection, run_id, capture_id, profile)
    return profile


def record_profile_checks(connection: psycopg.Connection, run_id: UUID, capture_id: UUID,
                          profile: dict, *, include_calendar_placeholder: bool = True) -> None:
    """Guarda el perfil, la publicación evaluará DQ-09 por mes completo, aparte."""
    start, end = parse_date(profile["window_start"]), parse_date(profile["window_end"])
    for check in profile_checks(profile):
        if check["rule_code"] == "DQ-09" and not include_calendar_placeholder:
            continue
        record_quality_result(
            connection, run_id, rule_code=check["rule_code"], status=check["status"],
            details={"capture_id": str(capture_id), **check["details"]},
            period_start=start, period_end=end, provider=profile["provider"], series_code=profile["series_code"])
