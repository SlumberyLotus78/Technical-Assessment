"""Registro y etapas de intentos; el coordinador controla su transacción."""

from datetime import date
from uuid import UUID, uuid4

import psycopg

from grain_pipeline.persistence.database import database_error_message


RUN_STAGES = ("planning", "extraction", "quality", "silver", "gold", "publication")


def require_transactional_connection(connection: psycopg.Connection) -> None:
    """Exige que el coordinador pueda confirmar o revertir el conjunto de escrituras."""
    if connection.autocommit:
        raise ValueError("Las escrituras requieren una conexión transaccional.")


def begin_run(connection: psycopg.Connection, load_type: str,
              start_month: date | None = None, end_month: date | None = None) -> UUID:
    """Registra un intento running; sus condiciones de publicación se comprueban aparte."""
    require_transactional_connection(connection)
    if load_type not in {"historical", "incremental"}:
        raise ValueError("Tipo de carga incompatible.")
    if (start_month is None) != (end_month is None):
        raise ValueError("El intervalo de ejecución requiere ambos meses.")
    if start_month is not None:
        if (type(start_month) is not date or type(end_month) is not date
                or start_month.day != 1 or end_month.day != 1 or start_month > end_month):
            raise ValueError("El intervalo requiere meses iniciales válidos y ordenados.")
    run_id = uuid4()
    connection.execute(
        """INSERT INTO ops.runs (run_id, load_type, status, stage, start_month, end_month)
           VALUES (%s, %s, 'running', 'planning', %s, %s)""",
        (run_id, load_type, start_month, end_month))
    return run_id


def require_running_run(connection: psycopg.Connection, run_id: UUID) -> dict:
    """Bloquea la fila del intento para evitar escrituras tras su cierre."""
    require_transactional_connection(connection)
    row = connection.execute(
        "SELECT load_type, status, stage, start_month, end_month FROM ops.runs WHERE run_id = %s FOR UPDATE", (run_id,)
    ).fetchone()
    if row is None or row[1] != "running":
        raise ValueError("La operación requiere un intento existente en estado running.")
    return {"load_type": row[0], "status": row[1], "stage": row[2],
            "start_month": row[3], "end_month": row[4]}


def get_run_status(connection: psycopg.Connection, run_id: UUID) -> str:
    """Consulta el estado durable para evitar cerrar de nuevo un intento terminado."""
    row = connection.execute("SELECT status FROM ops.runs WHERE run_id = %s", (run_id,)).fetchone()
    if row is None:
        raise ValueError("El intento solicitado no existe.")
    return row[0]


def set_run_stage(connection: psycopg.Connection, run_id: UUID, stage: str) -> None:
    """Avanza la etapa de un intento activo, conservando un orden no decreciente."""
    if stage not in RUN_STAGES:
        raise ValueError("Etapa de ejecución incompatible.")
    current = require_running_run(connection, run_id)
    if RUN_STAGES.index(stage) < RUN_STAGES.index(current["stage"]):
        raise ValueError("La etapa de un intento no puede retroceder.")
    connection.execute("UPDATE ops.runs SET stage = %s WHERE run_id = %s", (stage, run_id))


def fail_run(connection: psycopg.Connection, run_id: UUID, stage: str, error: Exception) -> None:
    """Cierra un intento fallido con tipo de error y etapa, sin volcar detalles privados."""
    if stage not in RUN_STAGES:
        raise ValueError("Etapa de ejecución incompatible.")
    require_running_run(connection, run_id)
    # No utilizamos str(error): una excepción de un cliente externo puede contener una URL autenticada. Las métricas DQ explican sus incidencias.
    summary = database_error_message(error) if isinstance(error, psycopg.Error) else type(error).__name__
    connection.execute(
        """UPDATE ops.runs SET status = 'failed', stage = %s,
           finished_at = clock_timestamp(), error_summary = %s WHERE run_id = %s""",
        (stage, summary, run_id))
