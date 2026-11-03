"""Conservación local de capturas JSON, identificadas por ejecución."""

from datetime import date, datetime, timezone
import json
from pathlib import Path
from uuid import uuid4


def create_sample_directory(root: Path) -> Path:
    """Crea una carpeta nueva para evitar sobrescribir una muestra anterior."""
    # UTC identifica el momento de captura y la fecha de operación se decide aparte, en America/Mexico_City, al seleccionar el mes de la muestra.
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}_{uuid4().hex}"
    directory.mkdir(parents=True)
    return directory


def write_json(path: Path, document: dict) -> None:
    """Escribe un documento nuevo; rechaza reemplazar un archivo existente."""
    # Serializamos antes de abrir el archivo: un contenido incompatible no deja un archivo vacío. 'x' exige crear un archivo que todavía no exista.
    content = json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2)
    with path.open("x", encoding="utf-8", newline="\n") as destination:
        destination.write(content + "\n")


def save_capture(directory: Path, series: dict, kind: str, payload: dict,
                 start: date | None = None, end: date | None = None) -> Path:
    """Conserva el objeto recibido con contexto público de origen y ventana."""
    if kind not in {"metadata", "observations"}:
        raise ValueError("Tipo de captura no soportado.")
    if kind == "observations" and (start is None or end is None or start > end):
        raise ValueError("La captura de observaciones requiere una ventana válida.")
    document = {
        "provider": series["provider"],
        "series_code": series["code"],
        "kind": kind,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "window_start": start.isoformat() if start is not None else None,
        "window_end": end.isoformat() if end is not None else None,
        "payload": payload,
    }
    
    path = directory / f"{series['provider'].lower()}_{series['code']}_{kind}.json"
    write_json(path, document)
    return path
