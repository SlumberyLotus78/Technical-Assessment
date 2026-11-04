"""Perfil histórico consolidado, reutiliza los contratos y reglas de la carga."""

from datetime import date

from grain_pipeline.common.dates import month_end, months_between
from grain_pipeline.quality.calendar import check_fix_coverage
from grain_pipeline.quality.profiling import profile_observations
from grain_pipeline.sources.catalog import SERIES, get_series
from grain_pipeline.sources.observations import read_observations
from grain_pipeline.transformations.silver import prepare_observations


def profile_historical_captures(captures: list[dict], start: date, end: date) -> dict:
    """Resume todos los fragmentos por serie y evalúa cada mes FIX independientemente."""
    grouped = {(series["provider"], series["code"]): [] for series in SERIES}
    for capture in captures:
        if capture["kind"] == "observations":
            series = get_series(capture["provider"], capture["series_code"])
            grouped[(series["provider"], series["code"])].extend(read_observations(capture["payload"], series))
    profiles, coverage = [], []
    for series in SERIES:
        rows = grouped[(series["provider"], series["code"])]
        profile = profile_observations(rows, series, start, month_end(end))
        profiles.append(profile)
        if series["provider"] == "Banxico" and not profile["has_issues"]:
            typed = prepare_observations(rows, series, start, month_end(end))
            for month in months_between(start, end):
                monthly = [row for row in typed if row["observation_date"].replace(day=1) == month]
                coverage.append(check_fix_coverage(monthly, month))
    return {"start_month": start.isoformat(), "end_month": end.isoformat(), "profiles": profiles,
            "fix_monthly_coverage": coverage,
            "has_issues": any(profile["has_issues"] for profile in profiles)
                          or any(check["status"] != "passed" for check in coverage)}
