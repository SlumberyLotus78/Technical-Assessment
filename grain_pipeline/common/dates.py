"""Lectura de fechas de origen y operaciones de meses compartidas."""

# Calendar conoce la cantidad real de días de cada mes, incluidos años bisiestos.
import calendar
from datetime import date, datetime
import re

# Metadatos y extracción utilizan la misma zona para decidir qué mes está cerrado.
OPERATING_TIMEZONE = "America/Mexico_City"

def parse_date(value, *, iso: bool = True) -> date:
    """Lee YYYY-MM-DD o, con iso=False, DD/MM/YYYY y devuelve una fecha válida."""
    pattern = r"[0-9]{4}-[0-9]{2}-[0-9]{2}" if iso else r"[0-9]{2}/[0-9]{2}/[0-9]{4}"
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise ValueError("Formato de fecha inesperado.")
    try:
        # El formato puede ser correcto y la fecha imposible, como 31/02.
        if iso:
            return date.fromisoformat(value)
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        raise ValueError("Fecha de origen inválida.") from None


def parse_month(value: str) -> date:
    """Interpreta YYYY-MM como el primer día de ese mes."""
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}", value) is None:
        raise ValueError("El mes debe tener formato YYYY-MM.")
    return parse_date(value + "-01")


def shift_month(day: date, delta: int) -> date:
    """Desplaza meses calendario y devuelve el primer día del mes resultante."""
    # Convertimos año y mes en una posición de una secuencia de meses.
    ordinal = day.year * 12 + day.month - 1 + delta
    try:
        return date(ordinal // 12, ordinal % 12 + 1, 1)
    except ValueError:
        raise ValueError("El desplazamiento excede el rango de fechas permitido.") from None


def month_end(day: date) -> date:
    """Devuelve el último día calendario del mes indicado."""
    last_day = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=last_day)
