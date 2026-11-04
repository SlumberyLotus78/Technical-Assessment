"""DQ-09: comparación de fechas FIX utilizables contra evidencia independiente."""

from collections import Counter
from datetime import date
from decimal import Decimal

from grain_pipeline.sources.banking_calendar import banking_calendar_for_month


def check_fix_coverage(records: list[dict], month: date) -> dict:
    """Evalúa un mes completo; conserva faltantes, inesperados y duplicados."""
    reference = banking_calendar_for_month(month)
    if not isinstance(records, list):
        raise ValueError("La cobertura FIX requiere una lista de registros Silver.")
    dates, usable_dates, invalid_rows = [], set(), 0
    for row in records:
        # La regla también protege su uso directo fuera del constructor Gold.
        if not isinstance(row, dict) or type(row.get("observation_date")) is not date:
            invalid_rows += 1
            continue
        day, value = row["observation_date"], row.get("value")
        dates.append(day)
        if (row.get("provider") != "Banxico" or row.get("series_code") != "SF43718"
                or not isinstance(value, Decimal) or not value.is_finite() or value <= 0):
            invalid_rows += 1
        else:
            usable_dates.add(day)

    counts = Counter(dates)
    duplicates = sorted(day.isoformat() for day, count in counts.items() if count > 1)
    details = {"month": month.isoformat(), "observed_days": len(records),
               "observed_dates": sorted(day.isoformat() for day in usable_dates),
               "invalid_rows": invalid_rows, "duplicate_dates": duplicates}
    if reference is None:
        details.update(coverage_status="pending_banking_calendar", expected_days=None,
                       expected_dates=None, calendar_reference=None, evidence_urls=[])
        status = "failed" if invalid_rows or duplicates else "pending"
    else:
        expected = set(reference["expected_dates"])
        missing = sorted(day.isoformat() for day in expected - usable_dates)
        unexpected = sorted(day.isoformat() for day in set(dates) - expected)
        status = "failed" if invalid_rows or duplicates or missing or unexpected or not expected else "passed"
        details.update(expected_days=len(expected), expected_dates=sorted(day.isoformat() for day in expected),
                       missing_dates=missing, unexpected_dates=unexpected,
                       calendar_reference=reference["calendar_reference"],
                       evidence_urls=reference["evidence_urls"], verified_on=reference["verified_on"],
                       coverage_status="complete" if status == "passed" else "incomplete")
    return {"rule_code": "DQ-09", "status": status, "details": details}
