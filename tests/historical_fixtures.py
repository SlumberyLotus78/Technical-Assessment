"""Sesión HTTP ficticia para recorrer el histórico real del código sin usar APIs."""

from datetime import date
from unittest.mock import MagicMock, Mock

import requests

from grain_pipeline.common.dates import months_between
from grain_pipeline.sources.banking_calendar import banking_calendar_for_month
from grain_pipeline.sources.catalog import SERIES, get_series
from tests.fixtures import metadata_payload, metadata_record, observations_payload


CREDENTIALS = {"FRED_API_KEY": "fixture-fred-key", "BANXICO_TOKEN": "fixture-banxico-token"}


def json_response(payload, *, status=200, headers=None):
    """Representa una respuesta nueva; todas sus llamadas son inspeccionables."""
    response = Mock()
    response.status_code = status
    response.headers = {"Content-Type": "application/json", **(headers or {})}
    response.json.return_value = payload
    return response


def historical_session():
    """Devuelve metadatos ficticios amplios, precios 100 y FIX 20 en fechas de referencia."""
    session = MagicMock(spec=requests.Session)
    session.__enter__.return_value = session
    session.__exit__.return_value = False

    def get(url, *, params, headers, timeout, allow_redirects):
        if "api.stlouisfed.org" in url:
            series = get_series("FRED", params["series_id"])
            is_observations = url.endswith("series/observations")
            start = date.fromisoformat(params["observation_start"]) if is_observations else None
            end = date.fromisoformat(params["observation_end"]) if is_observations else None
        else:
            series = SERIES[3]
            parts = url.split("/")
            is_observations = "datos" in parts
            start = date.fromisoformat(parts[-2]) if is_observations else None
            end = date.fromisoformat(parts[-1]) if is_observations else None
        if not is_observations:
            record = metadata_record(series)
            if series["provider"] == "FRED":
                record.update(observation_start="1992-01-01", observation_end="2026-09-01")
            else:
                record.update(fechaInicio="12/11/1991", fechaFin="03/11/2026")
            return json_response(metadata_payload(series, record))
        months = months_between(start, end.replace(day=1))
        if series["provider"] == "FRED":
            rows = [{"date": month.isoformat(), "value": "100"} for month in months]
        else:
            days = [day for month in months for day in banking_calendar_for_month(month)["expected_dates"]]
            rows = [{"fecha": day.strftime("%d/%m/%Y"), "dato": "20"} for day in days]
        return json_response(observations_payload(series, rows))

    session.get.side_effect = get
    return session
