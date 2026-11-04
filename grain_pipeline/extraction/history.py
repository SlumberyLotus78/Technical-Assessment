"""Capturas de extracción histórica; la coordinación decide cuándo registrarlas."""

from datetime import date
from pathlib import Path

import requests

from grain_pipeline.extraction.raw import save_capture
from grain_pipeline.sources.contracts import read_series_record
from grain_pipeline.sources.metadata import fetch_metadata_payload
from grain_pipeline.sources.observations import fetch_observations


def capture_historical_metadata(session: requests.Session, series: dict, credentials: dict,
                                 directory: Path) -> Path:
    """Conserva el registro nativo o la respuesta incompatible para diagnosticar el fallo."""
    payload = fetch_metadata_payload(session, series, credentials)
    try:
        record = read_series_record(payload, series)
    except ValueError:
        # La captura de un intento fallido conserva el objeto efectivamente recibido. El contrato posterior lo rechazará antes de publicar.
        record = payload
    destination = directory / "metadata"
    destination.mkdir(parents=True, exist_ok=True)
    return save_capture(destination, series, "metadata", record)


def capture_historical_observations(session: requests.Session, series: dict, credentials: dict,
                                     directory: Path, start: date, end: date) -> Path:
    """Guarda cada fragmento completo antes de validar su contrato de observaciones."""
    payload = fetch_observations(session, series, start, end, credentials)
    destination = directory / "observations" / f"{start.isoformat()}_{end.isoformat()}"
    destination.mkdir(parents=True, exist_ok=True)
    return save_capture(destination, series, "observations", payload, start, end)
