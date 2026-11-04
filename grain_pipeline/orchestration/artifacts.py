"""Manifiestos y perfiles de capturas; resultados locales posteriores al cierre SQL."""

from datetime import date, datetime, timezone
import logging
from pathlib import Path
from uuid import UUID

import psycopg

from grain_pipeline.extraction.raw import write_json
from grain_pipeline.orchestration.profiling import profile_capture_window
from grain_pipeline.persistence.captures import read_registered_capture


LOGGER = logging.getLogger(__name__)


def write_capture_manifest(connection: psycopg.Connection, run_id: UUID, capture_ids: list[UUID],
                            bronze_root: Path, directory: Path) -> list[dict]:
    """Revalida las capturas y escribe su relación con el intento; devuelve sus contenidos."""
    captures = [read_registered_capture(connection, capture_id, bronze_root) for capture_id in capture_ids]
    connection.commit()
    write_json(directory / "extraction_manifest.json", {
        "run_id": str(run_id), "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "captures": [{"capture_id": str(capture_id), "provider": capture["provider"],
                      "series_code": capture["series_code"], "kind": capture["kind"],
                      "storage_path": capture["storage_path"], "sha256": capture["content_sha256"]}
                     for capture_id, capture in zip(capture_ids, captures)]})
    return captures


def write_window_profile(run_id: UUID, captures: list[dict], start: date, end: date,
                          directory: Path, filename: str) -> None:
    """Perfila únicamente la ventana recibida; el publicador verificará luego el estado completo."""
    profile = profile_capture_window(captures, start, end)
    write_json(directory / filename, {"run_id": str(run_id), **profile})


def write_run_result(directory: Path, result: dict, *, filename: str = "publication_result.json") -> None:
    """Una exportación local fallida no cambia el resultado SQL ya confirmado."""
    try:
        write_json(directory / filename, result)
    except OSError:
        LOGGER.warning("Ejecución confirmada | no se pudo crear el resumen local | ejecución: %s", result["run_id"])
