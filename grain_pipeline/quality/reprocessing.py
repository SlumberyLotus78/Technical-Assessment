"""Límites del reproceso explícito de meses ya publicados."""

from datetime import date

from grain_pipeline.quality.windows import validate_closed_period


def validate_reprocessing_period(watermark: dict | None, start: date, end: date, *, as_of: date) -> None:
    """Una corrección no inicializa el producto ni amplía su intervalo."""
    validate_closed_period(start, end, as_of=as_of)
    if watermark is None:
        raise ValueError("El reproceso requiere un histórico publicado hasta Gold.")
    if start < watermark["start_month"] or end > watermark["published_through_month"]:
        raise ValueError("El reproceso debe quedar dentro del intervalo ya publicado.")
