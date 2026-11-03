"""Selección temporal para una muestra pequeña de diagnóstico."""

from datetime import date

from grain_pipeline.common.dates import month_end, shift_month
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.contracts import read_metadata_range


# Tres meses permiten inspeccionar varios registros de cada serie mensual.
FRED_SAMPLE_MONTHS = 3


def sample_window(series: dict, month: date) -> tuple[date, date]:
    """Propone tres meses FRED o un mes FIX, con el mismo mes de terminación."""
    if month.day != 1:
        raise ValueError("El mes de muestra debe identificarse con su primer día.")
    if series["provider"] == "FRED":
        start = shift_month(month, -(FRED_SAMPLE_MONTHS - 1))
    elif series["provider"] == "Banxico":
        start = month
    else:
        raise ValueError("Proveedor de muestra no soportado.")
    return start, month_end(month)


def select_sample_month(entries: list[dict], today: date, requested: date | None = None) -> date:
    """Elige un mes cerrado candidato usando las últimas fechas declaradas."""
    # Cada entrada contiene la definición de serie y sus metadatos ya consultados.
    # Los conjuntos permiten comprobar que estén todos los códigos esperados.
    expected_codes = {series["code"] for series in SERIES}
    received_codes = [entry["series"]["code"] for entry in entries]
    if set(received_codes) != expected_codes or len(received_codes) != len(expected_codes):
        raise ValueError("La muestra requiere metadatos de las cuatro series, sin duplicados.")

    # today llega como argumento para que las pruebas controlen la fecha de referencia.
    last_closed = shift_month(today, -1)
    limits = [last_closed]
    ranges = {}
    for entry in entries:
        series = entry["series"]
        start, end = read_metadata_range(entry["metadata"], series)
        ranges[series["code"]] = (start, end)
        # Comparamos meses. Una fecha mensual identifica todo su periodo;
        # una fecha FIX identifica un día de publicación dentro de su mes.
        limits.append(end.replace(day=1))

    # La fuente con el último mes declarado más antiguo limita la muestra común.
    latest = min(limits)
    selected = requested if requested is not None else latest
    if selected.day != 1 or selected > latest:
        raise ValueError("El mes solicitado debe estar cerrado y dentro de los rangos declarados.")

    for entry in entries:
        series = entry["series"]
        reported_start, _ = ranges[series["code"]]
        window_start, _ = sample_window(series, selected)
        # FRED necesita tres meses; también comprobamos que ese inicio sea posible.
        if window_start < reported_start:
            raise ValueError(f"{series['code']}: el rango declarado no alcanza para la muestra propuesta.")
    return selected
