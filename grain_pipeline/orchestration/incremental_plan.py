"""Selección de la ventana incremental desde watermark y disponibilidad actual."""

from datetime import date

from grain_pipeline.common.dates import shift_month
from grain_pipeline.quality.incremental import validate_incremental_baseline, validate_review_months
from grain_pipeline.quality.windows import read_available_ranges


def plan_incremental_window(watermark: dict, entries: list[dict], *, as_of: date,
                             review_months: int, end_month: date | None = None) -> dict:
    """Incluye los meses nuevos y el solapamiento; no inicia ni modifica un histórico."""
    validate_review_months(review_months)
    validate_incremental_baseline(watermark, as_of=as_of)
    ranges = read_available_ranges(entries)
    # Los metadatos permiten proponer el último mes común. El calendario y la
    # cobertura de las observaciones todavía deben aprobarse antes de publicar.
    latest = min([shift_month(as_of, -1), *(last.replace(day=1) for _, last in ranges.values())])
    published = watermark["published_through_month"]
    if latest < published:
        raise ValueError("La disponibilidad declarada por una fuente retrocedió antes del watermark.")
    selected = latest if end_month is None else end_month
    if type(selected) is not date or selected.day != 1 or not published <= selected <= latest:
        raise ValueError("El mes final incremental debe estar entre el watermark y el último mes común cerrado.")
    if selected == published and review_months == 0:
        return {"start_month": None, "end_month": None, "latest_common_month": latest,
                "review_months": review_months, "has_work": False}
    if review_months:
        # Se cuentan meses ya publicados; los meses nuevos se agregan después
        # de ese solapamiento. Nunca se retrocede antes del inicio del producto.
        available_months = (published.year - watermark["start_month"].year) * 12 + published.month - watermark["start_month"].month + 1
        months_back = min(review_months, available_months) - 1
        start = shift_month(published, -months_back)
    else:
        start = shift_month(published, 1)
    return {"start_month": start, "end_month": selected, "latest_common_month": latest,
            "review_months": review_months, "has_work": True}
