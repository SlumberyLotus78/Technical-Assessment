"""Lectura de referencias oficiales, nunca deduce el calendario desde FIX."""

from datetime import date, timedelta
from hashlib import sha256
from importlib.resources import files
import json

from grain_pipeline.common.dates import month_end, parse_date


def banking_calendar_for_month(month: date) -> dict | None:
    """Devuelve fechas esperadas y evidencia, o None si el año no está revisado."""
    if type(month) is not date or month.day != 1:
        raise ValueError("El calendario requiere el primer día de un mes.")
    resource = files("grain_pipeline.sources.calendars").joinpath(f"{month.year}.json")
    if not resource.is_file():
        return None
    text = resource.read_text(encoding="utf-8").replace("\r\n", "\n")
    try:
        reference = json.loads(text)
        if (not isinstance(reference, dict) or type(reference["year"]) is not int
                or reference["year"] != month.year or reference["provider"] != "Banxico"
                or reference["series_code"] != "SF43718"
                or reference["weekend_days"] != [5, 6]):
            raise ValueError
        if any(not isinstance(reference[field], str) or not reference[field].strip()
               for field in ("version", "authority")):
            raise ValueError
        if parse_date(reference["verified_on"]) < parse_date(reference["published_on"]):
            raise ValueError
        urls = reference["evidence_urls"]
        if (not isinstance(urls, list) or not urls
                or any(not isinstance(url, str) or not url.startswith("https://") for url in urls)):
            raise ValueError
        closed_dates = reference["closed_dates"]
        if not isinstance(closed_dates, list):
            raise ValueError
        closed = {parse_date(value) for value in closed_dates}
        if len(closed) != len(closed_dates) or any(day.year != month.year for day in closed):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        # Un recurso roto es un error, no equivale a un año sin referencia.
        raise ValueError("La referencia del calendario bancario es incompatible.") from None

    days = (month + timedelta(days=offset) for offset in range(month_end(month).day))
    expected = tuple(day for day in days if day.weekday() < 5 and day not in closed)
    checksum = sha256(text.encode("utf-8")).hexdigest()
    return {"expected_dates": expected, "evidence_urls": urls,
            "verified_on": reference["verified_on"],
            "calendar_reference": f"{reference['version']}:sha256:{checksum}"}
