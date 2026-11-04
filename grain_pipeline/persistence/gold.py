"""Lectura Silver con procedencia verificada y escritura idempotente de Gold."""

from datetime import date
from pathlib import Path
from uuid import UUID

import psycopg

from grain_pipeline.common.dates import month_end
from grain_pipeline.persistence.captures import read_registered_capture
from grain_pipeline.persistence.catalog import verify_catalog
from grain_pipeline.persistence.runs import require_running_run
from grain_pipeline.quality.publication import observation_values, validate_silver_lineage
from grain_pipeline.sources.catalog import get_series
from grain_pipeline.sources.observations import read_observations
from grain_pipeline.transformations.gold import build_monthly_gold
from grain_pipeline.transformations.silver import prepare_observations


# Los nombres son constantes del modelo, nunca provienen de argumentos de usuario.
FX_FIELDS = ("provider", "series_code", "month", "average_fix", "observed_days", "expected_days", "calendar_reference")
GRAIN_FIELDS = ("provider", "series_code", "month", "fx_provider", "fx_series_code", "grain_price_usd_t",
                "average_fix_mxn_usd", "reference_mxn_t", "mom_change_pct", "yoy_change_pct")


def read_silver_observations(connection: psycopg.Connection, start: date, end: date,
                             bronze_root: Path) -> list[dict]:
    """Revalida los archivos usados por las filas vigentes antes de reutilizarlas."""
    fields = ("provider", "series_code", "observation_date", "value", "source_capture_id")
    rows = connection.execute(
        """SELECT provider, series_code, observation_date, value, source_capture_id
           FROM core.observations WHERE observation_date BETWEEN %s AND %s
           ORDER BY provider, series_code, observation_date""", (start, month_end(end))).fetchall()
    records = [dict(zip(fields, row)) for row in rows]
    originals = {}
    for capture_id in {row["source_capture_id"] for row in records}:
        capture = read_registered_capture(connection, capture_id, bronze_root)
        if capture["kind"] != "observations":
            raise ValueError("La procedencia Silver requiere una captura de observaciones.")
        series = get_series(capture["provider"], capture["series_code"])
        native = read_observations(capture["payload"], series)
        prepared = prepare_observations(native, series, capture["window_start"], capture["window_end"])
        originals[capture_id] = observation_values(prepared)
    validate_silver_lineage(records, originals)
    return records


def read_monthly_gold(connection: psycopg.Connection, start: date, end: date) -> dict:
    """Lee únicamente los campos analíticos para verificar la publicación completa."""
    result = {}
    for table, fields in (("fx_monthly", FX_FIELDS), ("grain_reference_monthly", GRAIN_FIELDS)):
        rows = connection.execute(
            f"SELECT {', '.join(fields)} FROM mart.{table} WHERE month BETWEEN %s AND %s "
            "ORDER BY provider, series_code, month", (start, end)).fetchall()
        result[table] = [dict(zip(fields, row)) for row in rows]
    return result


def save_monthly_gold(connection: psycopg.Connection, run_id: UUID, start: date, end: date,
                      bronze_root: Path, *, as_of: date) -> dict:
    """Recalcula desde Silver y escribe solo resultados nuevos o modificados, no hace commit."""
    run = require_running_run(connection, run_id)
    if run["stage"] != "gold":
        raise ValueError("La escritura Gold requiere un intento en su etapa gold.")
    verify_catalog(connection)
    records = read_silver_observations(connection, start, end, bronze_root)
    gold = build_monthly_gold(records, start, end, as_of=as_of)
    statements = {
        "fx_monthly": """INSERT INTO mart.fx_monthly AS current
            (provider, series_code, month, average_fix, observed_days, expected_days,
             calendar_reference, source_run_id, calculated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, clock_timestamp())
            ON CONFLICT (provider, series_code, month) DO UPDATE
            SET average_fix = EXCLUDED.average_fix, observed_days = EXCLUDED.observed_days,
                expected_days = EXCLUDED.expected_days, calendar_reference = EXCLUDED.calendar_reference,
                source_run_id = EXCLUDED.source_run_id, calculated_at = EXCLUDED.calculated_at
            WHERE (current.average_fix, current.observed_days, current.expected_days, current.calendar_reference)
               IS DISTINCT FROM (EXCLUDED.average_fix, EXCLUDED.observed_days, EXCLUDED.expected_days, EXCLUDED.calendar_reference)""",
        "grain_reference_monthly": """INSERT INTO mart.grain_reference_monthly AS current
            (provider, series_code, month, fx_provider, fx_series_code, grain_price_usd_t,
             average_fix_mxn_usd, reference_mxn_t, mom_change_pct, yoy_change_pct, source_run_id, calculated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, clock_timestamp())
            ON CONFLICT (provider, series_code, month) DO UPDATE
            SET fx_provider = EXCLUDED.fx_provider, fx_series_code = EXCLUDED.fx_series_code,
                grain_price_usd_t = EXCLUDED.grain_price_usd_t, average_fix_mxn_usd = EXCLUDED.average_fix_mxn_usd,
                reference_mxn_t = EXCLUDED.reference_mxn_t, mom_change_pct = EXCLUDED.mom_change_pct,
                yoy_change_pct = EXCLUDED.yoy_change_pct, source_run_id = EXCLUDED.source_run_id,
                calculated_at = EXCLUDED.calculated_at
            WHERE (current.fx_provider, current.fx_series_code, current.grain_price_usd_t,
                   current.average_fix_mxn_usd, current.reference_mxn_t, current.mom_change_pct, current.yoy_change_pct)
               IS DISTINCT FROM (EXCLUDED.fx_provider, EXCLUDED.fx_series_code, EXCLUDED.grain_price_usd_t,
                   EXCLUDED.average_fix_mxn_usd, EXCLUDED.reference_mxn_t, EXCLUDED.mom_change_pct, EXCLUDED.yoy_change_pct)"""}
    metrics = {}
    for table, fields in (("fx_monthly", FX_FIELDS), ("grain_reference_monthly", GRAIN_FIELDS)):
        params = [tuple(row[field] for field in fields) + (run_id,) for row in gold[table]]
        with connection.cursor() as cursor:
            cursor.executemany(statements[table], params)
            metrics[table] = {"received": len(params), "written": cursor.rowcount,
                              "unchanged": len(params) - cursor.rowcount}
    return {"data": gold, "metrics": metrics}
