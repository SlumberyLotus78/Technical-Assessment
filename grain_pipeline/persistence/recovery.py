"""Lecturas operativas y cierre de intentos abandonados; el coordinador posee el commit."""

from uuid import UUID

import psycopg

from grain_pipeline.common.dates import month_end
from grain_pipeline.persistence.quality import record_quality_result
from grain_pipeline.persistence.runs import fail_run


def read_attempt(connection: psycopg.Connection, run_id: UUID) -> dict:
    """Lee el intento bajo bloqueo de fila; nunca cambia estados terminados."""
    fields = ("load_type", "status", "stage", "start_month", "end_month", "started_at")
    row = connection.execute(
        "SELECT load_type, status, stage, start_month, end_month, started_at FROM ops.runs WHERE run_id = %s FOR UPDATE",
        (run_id,)).fetchone()
    if row is None:
        raise ValueError("La ejecución solicitada no existe.")
    return {"run_id": run_id, **dict(zip(fields, row))}


def read_attempt_captures(connection: psycopg.Connection, run_id: UUID) -> list[dict]:
    """Una recuperación fallida conserva la relación con las capturas de su origen."""
    ids = [row[0] for row in connection.execute(
        "SELECT capture_id FROM ops.raw_captures WHERE run_id = %s ORDER BY capture_id", (run_id,)).fetchall()]
    if not ids:
        link = connection.execute(
            """SELECT details FROM ops.dq_results WHERE run_id = %s AND rule_code = 'CTL-05'
               AND details->>'operation' = 'recovery' ORDER BY checked_at DESC LIMIT 1""", (run_id,)).fetchone()
        if link is not None:
            ids = [UUID(value) for value in link[0]["capture_ids"]]
    fields = ("capture_id", "provider", "series_code", "kind", "window_start", "window_end")
    return [dict(zip(fields, row)) for row in connection.execute(
        """SELECT capture_id, provider, series_code, kind, window_start, window_end
           FROM ops.raw_captures WHERE capture_id = ANY(%s) ORDER BY capture_id""", (ids,)).fetchall()]


def read_successful_recovery(connection: psycopg.Connection, source_id: UUID) -> UUID | None:
    """Permite repetir la solicitud sin crear otra publicación después del éxito."""
    row = connection.execute(
        """SELECT r.run_id FROM ops.runs r JOIN ops.dq_results d USING (run_id)
           WHERE d.rule_code = 'CTL-05' AND d.details->>'operation' = 'recovery'
             AND d.details->>'source_run_id' = %s AND r.status = 'succeeded'
           ORDER BY r.finished_at DESC LIMIT 1""", (str(source_id),)).fetchone()
    return None if row is None else row[0]


def has_newer_publication(connection: psycopg.Connection, attempt: dict) -> bool:
    """Evita que capturas de un intento antiguo reviertan una revisión posterior."""
    return connection.execute(
        "SELECT EXISTS (SELECT 1 FROM ops.runs WHERE status = 'succeeded' AND finished_at > %s)",
        (attempt["started_at"],)).fetchone()[0]


def close_abandoned_attempt(connection: psycopg.Connection, attempt: dict, decision: dict) -> None:
    """Se invoca solo después de adquirir el bloqueo exclusivo del producto."""
    if attempt["status"] != "running":
        return
    if attempt["start_month"] is not None:
        record_quality_result(connection, attempt["run_id"], rule_code="CTL-05", status="failed",
                              details={"operation": "interruption", **decision},
                              period_start=attempt["start_month"], period_end=month_end(attempt["end_month"]))
    fail_run(connection, attempt["run_id"], attempt["stage"], RuntimeError())
    connection.execute("UPDATE ops.runs SET error_summary = %s WHERE run_id = %s",
                       ("Interrupción detectada tras adquirir el bloqueo del producto.", attempt["run_id"]))
