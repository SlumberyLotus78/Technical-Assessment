"""Coordinación común de consultas y registro durable de cada captura."""

from datetime import date
import logging
from pathlib import Path
from uuid import UUID

import psycopg
import requests

from grain_pipeline.extraction.captures import capture_metadata, capture_observation_window
from grain_pipeline.persistence.captures import read_registered_capture, register_capture
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.contracts import validate_metadata_record
from grain_pipeline.sources.observations import read_observations
from grain_pipeline.sources.windows import yearly_query_windows


LOGGER = logging.getLogger(__name__)


def collect_metadata(connection: psycopg.Connection, session: requests.Session, credentials: dict,
                      run_id: UUID, bronze_root: Path, directory: Path) -> dict:
    """Conserva y registra metadatos antes del contrato, sin dejar SQL abierto entre peticiones."""
    capture_ids, entries = [], []
    for series in SERIES:
        LOGGER.info("Metadatos | %s | %s", series["provider"], series["code"])
        path = capture_metadata(session, series, credentials, directory)
        capture_id = register_capture(connection, run_id, path, bronze_root)
        connection.commit()
        capture = read_registered_capture(connection, capture_id, bronze_root)
        record = validate_metadata_record(capture["payload"], series)
        capture_ids.append(capture_id)
        entries.append({"series": series, "metadata": record})
        connection.commit()
    return {"capture_ids": capture_ids, "entries": entries}


def collect_observation_windows(connection: psycopg.Connection, session: requests.Session, credentials: dict,
                                run_id: UUID, bronze_root: Path, directory: Path,
                                start: date, end: date) -> list[UUID]:
    """Consulta la ventana que decidió el coordinador y conserva cada respuesta antes del contrato."""
    capture_ids = []
    for series in SERIES:
        for first, last in yearly_query_windows(start, end):
            LOGGER.info("Observaciones | %s | %s | %s a %s", series["provider"], series["code"], first, last)
            path = capture_observation_window(session, series, credentials, directory, first, last)
            capture_id = register_capture(connection, run_id, path, bronze_root)
            connection.commit()
            capture = read_registered_capture(connection, capture_id, bronze_root)
            read_observations(capture["payload"], series)
            capture_ids.append(capture_id)
            connection.commit()
    return capture_ids
