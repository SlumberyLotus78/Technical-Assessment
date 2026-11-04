"""Escritura Silver con validación de procedencia y actualización por clave natural."""

from pathlib import Path
from uuid import UUID

import psycopg

from grain_pipeline.common.dates import month_end
from grain_pipeline.persistence.captures import read_registered_capture
from grain_pipeline.persistence.catalog import verify_catalog
from grain_pipeline.persistence.runs import require_running_run
from grain_pipeline.sources.catalog import get_series
from grain_pipeline.sources.observations import read_observations
from grain_pipeline.transformations.silver import prepare_observations


def save_capture_observations(connection: psycopg.Connection, run_id: UUID,
                              capture_id: UUID, bronze_root: Path) -> dict:
    """Prepara toda la captura y escribe solo filas nuevas o con valor revisado."""
    run = require_running_run(connection, run_id)
    verify_catalog(connection)
    capture = read_registered_capture(connection, capture_id, bronze_root)
    if capture["kind"] != "observations":
        raise ValueError("Silver requiere una captura de observaciones.")
    if (run["start_month"] is None or capture["window_start"] < run["start_month"]
            or capture["window_end"] > month_end(run["end_month"])):
        raise ValueError("La captura no está contenida en el intervalo planificado del intento.")
    series = get_series(capture["provider"], capture["series_code"])
    records = read_observations(capture["payload"], series)
    prepared = prepare_observations(records, series, capture["window_start"], capture["window_end"])
    # Se valida el conjunto completo antes de ejecutar la primera escritura.
    params = [(row["provider"], row["series_code"], row["observation_date"], row["value"],
               capture_id, run_id, run_id) for row in prepared]
    with connection.cursor() as cursor:
        # EXCLUDED es la fila propuesta. WHERE deja sin UPDATE las filas cuyo valor numérico no cambió, conservando su procedencia e instantes.
        cursor.executemany(
            """INSERT INTO core.observations
               (provider, series_code, observation_date, value, source_capture_id, created_run_id, updated_run_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (provider, series_code, observation_date) DO UPDATE
               SET value = EXCLUDED.value, source_capture_id = EXCLUDED.source_capture_id,
                   updated_run_id = EXCLUDED.updated_run_id, updated_at = clock_timestamp()
               WHERE core.observations.value IS DISTINCT FROM EXCLUDED.value""", params)
        written = cursor.rowcount
    return {"received": len(prepared), "written": written, "unchanged": len(prepared) - written}
