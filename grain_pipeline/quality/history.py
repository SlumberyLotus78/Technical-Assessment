"""Condiciones de la carga histórica explícita, anteriores a consultar observaciones."""

from datetime import date

from grain_pipeline.common.dates import months_between
from grain_pipeline.sources.banking_calendar import banking_calendar_for_month
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.contracts import read_metadata_range, validate_metadata_record


def validate_historical_period(start: date, end: date, *, as_of: date) -> None:
    """Exige meses iniciales ordenados y un extremo final ya cerrado."""
    months_between(start, end)
    if type(as_of) is not date or end >= as_of.replace(day=1):
        raise ValueError("La carga histórica requiere un intervalo de meses cerrados.")


def validate_historical_availability(entries: list[dict], start: date, end: date, *, as_of: date) -> None:
    """Comprueba catálogo, calendario y disponibilidad de todas las fechas requeridas."""
    validate_historical_period(start, end, as_of=as_of)
    expected = {(series["provider"], series["code"]) for series in SERIES}
    received = [(entry["series"]["provider"], entry["series"]["code"]) for entry in entries]
    if set(received) != expected or len(received) != len(expected):
        raise ValueError("El histórico requiere metadatos de las cuatro series, sin duplicados.")
    expected_fix_dates = []
    for month in months_between(start, end):
        calendar = banking_calendar_for_month(month)
        if calendar is None:
            raise ValueError(f"Falta una referencia bancaria revisada para el año {month.year}.")
        expected_fix_dates.extend(calendar["expected_dates"])
    if not expected_fix_dates:
        raise ValueError("El intervalo no tiene fechas bancarias esperadas.")
    for entry in entries:
        series = entry["series"]
        record = validate_metadata_record(entry["metadata"], series)
        first, last = read_metadata_range(record, series)
        required_first, required_last = ((start, end) if series["frequency"] == "monthly"
                                         else (min(expected_fix_dates), max(expected_fix_dates)))
        if first > required_first or last < required_last:
            raise ValueError(f"{series['code']}: la disponibilidad declarada no cubre el histórico solicitado.")
