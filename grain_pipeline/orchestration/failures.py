"""Registro de fallos del coordinador, conservando cierres que ya hizo el publicador."""

from datetime import date
from uuid import UUID

import psycopg

from grain_pipeline.common.dates import month_end
from grain_pipeline.persistence.quality import record_quality_result
from grain_pipeline.persistence.runs import fail_run, get_run_status


def record_attempt_failure(connection: psycopg.Connection, run_id: UUID, stage: str, step: str,
                            error: Exception, *, start: date | None, end: date | None) -> None:
    """Revierte SQL pendiente y cierra solo intentos activos, sin texto privado de excepciones."""
    if connection.closed or connection.broken:
        return
    connection.rollback()
    if get_run_status(connection, run_id) != "running":
        connection.rollback()
        return
    if start is not None and end is not None:
        rules = {"initialization": "CTL-01", "baseline": "CTL-01", "planning": "CTL-02",
                 "availability": "CTL-02", "metadata": "SRC-02", "observations": "SRC-03"}
        code = "PUB-01" if stage == "quality" else rules.get(step, "CTL-04")
        record_quality_result(connection, run_id, rule_code=code, status="failed",
                              details={"stage": stage, "step": step, "error_type": type(error).__name__},
                              period_start=start, period_end=month_end(end))
    fail_run(connection, run_id, stage, error)
    connection.commit()
