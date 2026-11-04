"""Precondiciones del incremental y límites explícitos de revisión de publicaciones."""

from datetime import date

from grain_pipeline.common.dates import months_between


DEFAULT_REVIEW_MONTHS = 3
MAX_REVIEW_MONTHS = 12


def validate_review_months(review_months: int) -> None:
    """Limita el solapamiento automático, las correcciones antiguas requieren reproceso."""
    if type(review_months) is not int or not 0 <= review_months <= MAX_REVIEW_MONTHS:
        raise ValueError("La revisión incremental debe indicar entre cero y doce meses.")


def validate_incremental_baseline(watermark: dict | None, *, as_of: date) -> None:
    """Exige un intervalo inicializado de meses cerrados antes de planear consultas."""
    if watermark is None:
        raise ValueError("El incremental requiere una carga histórica publicada hasta Gold.")
    first, last = watermark["start_month"], watermark["published_through_month"]
    months_between(first, last)
    if type(as_of) is not date or last >= as_of.replace(day=1):
        raise ValueError("El watermark debe contener únicamente meses ya cerrados.")
