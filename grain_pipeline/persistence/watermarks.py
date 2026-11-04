"""Lectura del avance publicado y cierre de éxito, sin commits independientes."""

from datetime import date
from pathlib import Path
from uuid import UUID

import psycopg

from grain_pipeline.persistence.gold import read_monthly_gold, read_silver_observations
from grain_pipeline.persistence.runs import require_running_run
from grain_pipeline.quality.publication import plan_publication, validate_stored_gold
from grain_pipeline.transformations.gold import build_monthly_gold


PRODUCT_NAME = "grain_reference_mxn"


def read_watermark(connection: psycopg.Connection) -> dict | None:
    """Comprueba que el avance proceda de un histórico y de publicaciones exitosas."""
    fields = ("start_month", "published_through_month", "initial_run_id", "last_run_id", "updated_at")
    row = connection.execute(
        """SELECT start_month, published_through_month, initial_run_id, last_run_id, updated_at
           FROM ops.watermarks WHERE pipeline_name = %s FOR UPDATE""", (PRODUCT_NAME,)).fetchone()
    if row is None:
        return None
    state = dict(zip(fields, row))
    initial = connection.execute(
        "SELECT load_type, status, start_month, end_month FROM ops.runs WHERE run_id = %s",
        (state["initial_run_id"],)).fetchone()
    last = connection.execute("SELECT status, stage FROM ops.runs WHERE run_id = %s",
                              (state["last_run_id"],)).fetchone()
    if (initial is None or initial[:2] != ("historical", "succeeded")
            or initial[2] != state["start_month"] or initial[3] > state["published_through_month"]
            or last != ("succeeded", "publication")):
        raise ValueError("El watermark no está respaldado por las ejecuciones publicadas requeridas.")
    return state


def complete_publication(connection: psycopg.Connection, run_id: UUID, previous: dict | None,
                          plan: dict, bronze_root: Path, *, as_of: date) -> None:
    """Actualiza watermark y éxito dentro de la misma transacción que Silver y Gold."""
    run = require_running_run(connection, run_id)
    if run["stage"] != "publication":
        raise ValueError("El cierre de éxito requiere la etapa publication.")
    current = read_watermark(connection)
    if current != previous or plan_publication(run, current, as_of=as_of) != plan:
        raise ValueError("El avance publicado cambió respecto del plan validado.")
    # También se protege el uso directo del finalizador: poner una ejecución
    # en etapa publication no acredita que existan datos correctos hasta Gold.
    records = read_silver_observations(connection, plan["start_month"], plan["end_month"], bronze_root)
    expected = build_monthly_gold(records, plan["start_month"], plan["end_month"], as_of=as_of)
    validate_stored_gold(expected, read_monthly_gold(connection, plan["start_month"], plan["end_month"]))
    initial_id = run_id if current is None else current["initial_run_id"]
    connection.execute(
        """INSERT INTO ops.watermarks
           (pipeline_name, start_month, published_through_month, initial_run_id, last_run_id, updated_at)
           VALUES (%s, %s, %s, %s, %s, clock_timestamp())
           ON CONFLICT (pipeline_name) DO UPDATE
           SET published_through_month = EXCLUDED.published_through_month,
               last_run_id = EXCLUDED.last_run_id, updated_at = EXCLUDED.updated_at""",
        (PRODUCT_NAME, plan["start_month"], plan["end_month"], initial_id, run_id))
    connection.execute(
        """UPDATE ops.runs SET status = 'succeeded', stage = 'publication',
           finished_at = clock_timestamp(), error_summary = NULL WHERE run_id = %s""", (run_id,))
