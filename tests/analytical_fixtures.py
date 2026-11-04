"""Gold ficticio calculado por las transformaciones productivas para probar el análisis."""

from datetime import date
from decimal import Decimal

from grain_pipeline.common.dates import months_between
from grain_pipeline.sources.banking_calendar import banking_calendar_for_month
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.transformations.gold import build_monthly_gold


def analytical_rows(start=date(2026, 7, 1), end=date(2026, 9, 1), *, overrides=None):
    overrides = {} if overrides is None else overrides
    records = []
    for month in months_between(start, end):
        for series in SERIES:
            days = [month] if series["frequency"] == "monthly" else banking_calendar_for_month(month)["expected_dates"]
            for day in days:
                value = overrides.get((series["code"], day), "100" if series["frequency"] == "monthly" else "20")
                records.append(dict(provider=series["provider"], series_code=series["code"], observation_date=day, value=Decimal(value)))
    gold = build_monthly_gold(records, start, end, as_of=date(2026, 11, 3))
    fixes = {row["month"]: row for row in gold["fx_monthly"]}
    names = {series["code"]: series["name"] for series in SERIES}
    return [dict(row, name=names[row["series_code"]], fx_average=fixes[row["month"]]["average_fix"],
                 observed_days=fixes[row["month"]]["observed_days"], expected_days=fixes[row["month"]]["expected_days"],
                 calendar_reference=fixes[row["month"]]["calendar_reference"]) for row in gold["grain_reference_monthly"]]
