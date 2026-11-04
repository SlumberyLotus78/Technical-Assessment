"""Capturas completas ficticias para probar publicación, sin APIs ni secretos."""

from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from grain_pipeline.common.dates import month_end, months_between
from grain_pipeline.extraction.raw import save_capture
from grain_pipeline.sources.banking_calendar import banking_calendar_for_month
from grain_pipeline.sources.catalog import SERIES
from tests.fixtures import metadata_record, observations_payload


def publication_capture_files(root: Path, start: date, end: date, *, overrides: dict | None = None) -> list[Path]:
    """Crea cuatro metadatos y cuatro respuestas nativas con precios 100 y FIX 20."""
    directory = root / uuid4().hex
    directory.mkdir()
    overrides = {} if overrides is None else overrides
    paths = []
    for series in SERIES:
        metadata = metadata_record(series)
        if series["provider"] == "FRED":
            metadata.update(observation_start=f"{start.year}-01-01", observation_end=f"{end.year}-12-01")
            rows = [{"date": month.isoformat(), "value": overrides.get((series["code"], month), "100")}
                    for month in months_between(start, end)]
        else:
            metadata.update(fechaInicio=f"01/01/{start.year}", fechaFin=f"31/12/{end.year}")
            days = []
            for month in months_between(start, end):
                calendar = banking_calendar_for_month(month)
                if calendar is None:
                    # Una fuente ficticia puede devolver datos de un año aún
                    # no revisado. La regla real deberá dejarlos pendientes.
                    candidates = [month + timedelta(days=offset) for offset in range(month_end(month).day)]
                    days.extend(day for day in candidates if day.weekday() < 5)
                else:
                    days.extend(calendar["expected_dates"])
            rows = [{"fecha": day.strftime("%d/%m/%Y"), "dato": overrides.get((series["code"], day), "20")}
                    for day in days]
        paths.append(save_capture(directory, series, "metadata", metadata))
        paths.append(save_capture(directory, series, "observations", observations_payload(series, rows), start, month_end(end)))
    return paths
