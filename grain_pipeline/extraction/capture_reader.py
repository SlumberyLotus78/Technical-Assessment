"""Lectura de capturas Bronze con contexto tipado e integridad de archivo."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from grain_pipeline.common.dates import parse_date
from grain_pipeline.sources.catalog import get_series


def read_capture(path: Path, bronze_root: Path) -> dict:
    """Lee una captura dentro de Bronze, el payload conserva su contenido original."""
    root = bronze_root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    
    if not resolved.is_relative_to(root) or not resolved.is_file() or resolved.suffix.lower() != ".json":
        raise ValueError("La captura debe ser un archivo JSON dentro de la raíz Bronze.")
    content = resolved.read_bytes()
    try:
        document = json.loads(content.decode("utf-8-sig"))
    except (ValueError, UnicodeError):
        raise ValueError("El archivo de captura no contiene JSON UTF-8 válido.") from None
    if not isinstance(document, dict) or "payload" not in document:
        raise ValueError("La captura no contiene la estructura de contexto requerida.")
    series = get_series(document.get("provider"), document.get("series_code"))
    kind = document.get("kind")
    if kind not in {"metadata", "observations"}:
        raise ValueError("Tipo de captura incompatible.")
    try:
        captured_at = datetime.fromisoformat(document.get("captured_at_utc"))
    except (ValueError, TypeError):
        raise ValueError("Instante de captura inválido.") from None
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("El instante de captura requiere una zona horaria explícita.")

    start, end = document.get("window_start"), document.get("window_end")
    if kind == "observations":
        start, end = parse_date(start), parse_date(end)
        if start > end:
            raise ValueError("La ventana de la captura está invertida.")
    elif start is not None or end is not None:
        raise ValueError("Una captura de metadatos no debe declarar ventana de observaciones.")

    # Hash y payload corresponden a los mismos bytes leídos una sola vez.
    # La ruta almacenada se interpreta respecto de una raíz Bronze estable.
    return {"provider": series["provider"], "series_code": series["code"], "kind": kind,
            "storage_path": resolved.relative_to(root).as_posix(),
            "content_sha256": sha256(content).hexdigest(),
            "captured_at": captured_at.astimezone(timezone.utc),
            "window_start": start, "window_end": end, "payload": document["payload"]}
