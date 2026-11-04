"""Registro de procedencia Bronze y lectura de capturas previamente registradas."""

from pathlib import Path
from uuid import UUID, uuid4

import psycopg

from grain_pipeline.extraction.capture_reader import read_capture
from grain_pipeline.persistence.runs import require_running_run


CAPTURE_FIELDS = ("provider", "series_code", "kind", "storage_path", "content_sha256",
                  "captured_at", "window_start", "window_end")


def get_capture_record(connection: psycopg.Connection, capture_id: UUID) -> dict:
    """Obtiene el contexto registrado; el payload permanece en el archivo Bronze."""
    row = connection.execute(
        """SELECT provider, series_code, kind, storage_path, content_sha256,
           captured_at, window_start, window_end FROM ops.raw_captures WHERE capture_id = %s""",
        (capture_id,)).fetchone()
    if row is None:
        raise ValueError("La captura solicitada no está registrada.")
    # zip empareja cada nombre con el valor de su columna, en el mismo orden.
    return dict(zip(CAPTURE_FIELDS, row))


def register_capture(connection: psycopg.Connection, run_id: UUID,
                     path: Path, bronze_root: Path) -> UUID:
    """Registra un archivo nuevo o reutiliza su registro si el contenido coincide."""
    require_running_run(connection, run_id)
    capture = read_capture(path, bronze_root)
    capture_id = uuid4()
    # El * expande los valores del contexto siguiendo el orden de CAPTURE_FIELDS.
    row = connection.execute(
        """INSERT INTO ops.raw_captures
           (capture_id, run_id, provider, series_code, kind, storage_path, content_sha256,
            captured_at, window_start, window_end)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (storage_path) DO NOTHING RETURNING capture_id""",
        (capture_id, run_id, *(capture[field] for field in CAPTURE_FIELDS))).fetchone()
    if row is not None:
        return row[0]

    existing_id = connection.execute(
        "SELECT capture_id FROM ops.raw_captures WHERE storage_path = %s", (capture["storage_path"],)
    ).fetchone()[0]
    if get_capture_record(connection, existing_id) != {field: capture[field] for field in CAPTURE_FIELDS}:
        raise ValueError("El archivo de una captura registrada cambió; debe conservarse su evidencia.")
    # El registro conserva la ejecución que capturó originalmente el archivo.
    # Un reproceso puede reutilizar ese ID sin reasignar la procedencia.
    return existing_id


def read_registered_capture(connection: psycopg.Connection, capture_id: UUID, bronze_root: Path) -> dict:
    """Comprueba hash y contexto contra el registro antes de procesar sus datos."""
    registered = get_capture_record(connection, capture_id)
    capture = read_capture(bronze_root / registered["storage_path"], bronze_root)
    if any(capture[field] != registered[field] for field in CAPTURE_FIELDS):
        raise ValueError("La captura no coincide con el hash y contexto registrados.")
    return capture
