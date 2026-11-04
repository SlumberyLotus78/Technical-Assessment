"""Reglas de aceptación de registros y traducción del perfil a resultados DQ."""

from datetime import date

from grain_pipeline.quality.profiling import profile_observations


def validate_observations(records: list[dict], series: dict, start: date, end: date) -> dict:
    """Exige registros válidos para tiparlos, la cobertura FIX se certifica aparte."""
    if not isinstance(records, list) or any(not isinstance(row, dict) or "date" not in row
                                           or "value" not in row for row in records):
        raise ValueError("Las observaciones requieren los campos comunes date y value.")
    profile = profile_observations(records, series, start, end)
    if profile["has_issues"]:
        raise ValueError(f"{series['code']}: las observaciones tienen incidencias de calidad.")
    return profile


def profile_checks(profile: dict) -> list[dict]:
    """Representa las reglas del perfil con códigos estables y métricas públicas."""
    checks = [{"rule_code": "SRC-03", "status": "passed" if profile["rows"] else "failed",
               "details": {"rows": profile["rows"]}}]
    fields = (("DQ-01", "invalid_dates"), ("DQ-02", "outside_window"),
              ("DQ-03", "invalid_values"), ("DQ-04", "missing_values"),
              ("DQ-05", "non_positive_values"), ("DQ-06", "duplicate_dates"))
    for code, field in fields:
        count = profile[field]
        checks.append({"rule_code": code, "status": "failed" if count else "passed",
                       "details": {field: count}})
    if profile["expected_months"] is not None:
        checks.append({"rule_code": "DQ-07",
                       "status": "failed" if profile["non_month_start_dates"] else "passed",
                       "details": {"non_month_start_dates": profile["non_month_start_dates"]}})
        checks.append({"rule_code": "DQ-08", "status": "failed" if profile["missing_months"] else "passed",
                       "details": {"expected_months": profile["expected_months"],
                                   "missing_months": profile["missing_months"]}})
    else:
        checks.append({"rule_code": "DQ-09", "status": "pending",
                       "details": {"coverage_status": "pending_banking_calendar"}})
    return checks
