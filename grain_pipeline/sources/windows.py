"""Ventanas de consulta acotadas, compartibles por los coordinadores de carga."""

from datetime import date

from grain_pipeline.common.dates import month_end, months_between


def yearly_query_windows(start_month: date, end_month: date) -> list[tuple[date, date]]:
    """Divide meses completos por año calendario, sin solapamientos ni huecos."""
    months_between(start_month, end_month)
    return [(max(start_month, date(year, 1, 1)), min(month_end(end_month), date(year, 12, 31)))
            for year in range(start_month.year, end_month.year + 1)]
