"""Reglas de tipos, claves y dependencias del intervalo mensual completo."""

from datetime import date
from decimal import Decimal

from grain_pipeline.common.dates import month_end, months_between
from grain_pipeline.sources.catalog import SERIES, get_series


def validate_gold_inputs(records: list[dict], start: date, end: date, as_of: date) -> dict:
    """Indexa Silver sin descartar filas y exige los tres granos de cada mes."""
    months = months_between(start, end)
    if type(as_of) is not date or end >= as_of.replace(day=1):
        raise ValueError("Gold requiere únicamente meses cerrados a la fecha de operación.")
    if not isinstance(records, list):
        raise ValueError("Gold requiere una lista de observaciones Silver.")
    indexed = {}
    for row in records:
        if (not isinstance(row, dict) or not {"provider", "series_code", "observation_date", "value"} <= row.keys()
                or not isinstance(row["provider"], str) or not isinstance(row["series_code"], str)):
            raise ValueError("Gold requiere proveedor, serie, fecha y valor Silver.")
        series = get_series(row["provider"], row["series_code"])
        day, value = row["observation_date"], row["value"]
        if type(day) is not date or not start <= day <= month_end(end):
            raise ValueError("Gold recibió una fecha incompatible con el intervalo.")
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            raise ValueError("Gold requiere valores Decimal finitos y positivos.")
        if series["frequency"] == "monthly" and day.day != 1:
            raise ValueError("El precio mensual debe identificar el primer día de su mes.")
        key = (row["provider"], row["series_code"], day)
        if key in indexed:
            # Este control cubre duplicados entre capturas o fragmentos unidos.
            raise ValueError("El conjunto Silver contiene una clave duplicada.")
        indexed[key] = row
    for month in months:
        for series in SERIES:
            if series["frequency"] == "monthly" and (series["provider"], series["code"], month) not in indexed:
                raise ValueError(f"Falta el precio mensual requerido: {series['code']} / {month:%Y-%m}.")
    return indexed
