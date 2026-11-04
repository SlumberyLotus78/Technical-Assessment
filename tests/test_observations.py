"""Contratos de observaciones y parámetros de consulta con transporte simulado."""

from copy import deepcopy
from datetime import date
import unittest
from unittest.mock import Mock, patch

from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.observations import fetch_observations, read_observations
from tests.fixtures import observations_payload


CREDENTIALS = {"FRED_API_KEY": "fixture-fred-key", "BANXICO_TOKEN": "fixture-banxico-token"}


class ObservationSourceTests(unittest.TestCase):
    """Ejecuta el adaptador real sustituyendo únicamente la comunicación externa."""

    def test_fred_requests_original_values_for_the_requested_window(self):
        series, session = SERIES[0], Mock()
        payload = observations_payload(series)
        with patch("grain_pipeline.sources.observations.request_json", return_value=payload) as request:
            result = fetch_observations(session, series, date(2026, 7, 1),
                                        date(2026, 9, 30), CREDENTIALS)
        self.assertIs(result, payload)
        request.assert_called_once_with(
            session, "FRED", "series/observations",
            {"series_id": series["code"], "file_type": "json",
             "observation_start": "2026-07-01", "observation_end": "2026-09-30",
             "sort_order": "asc", "units": "lin", "output_type": 1,
             "limit": 100000, "offset": 0}, CREDENTIALS)

    def test_banxico_uses_iso_request_dates_and_preserves_response_dates(self):
        series, session = SERIES[3], Mock()
        payload = observations_payload(series)
        with patch("grain_pipeline.sources.observations.request_json", return_value=payload) as request:
            result = fetch_observations(session, series, date(2026, 9, 1),
                                        date(2026, 9, 30), CREDENTIALS)
        request.assert_called_once_with(session, "Banxico", "series/SF43718/datos/2026-09-01/2026-09-30",
                                        {"locale": "es"}, CREDENTIALS)
        self.assertEqual(read_observations(result, series)[0],
                         {"date": "01/09/2026", "value": "18.1234"})

    def test_invalid_range_or_provider_prevents_the_request(self):
        other = {**SERIES[0], "provider": "Other"}
        cases = ((SERIES[0], date(2026, 9, 2), date(2026, 9, 1)),
                 (other, date(2026, 9, 1), date(2026, 9, 30)))
        with patch("grain_pipeline.sources.observations.request_json") as request:
            for series, start, end in cases:
                with self.subTest(provider=series["provider"]):
                    with self.assertRaises(ValueError):
                        fetch_observations(Mock(), series, start, end, CREDENTIALS)
            request.assert_not_called()

    def test_fred_rejects_partial_pages_changed_units_and_invalid_shapes(self):
        valid = observations_payload(SERIES[0])
        cases = ([], {"error_code": 400}, {},
                 {**valid, "observations": {}},
                 {**valid, "count": 4}, {**valid, "count": "3"},
                 {**valid, "count": True}, {**valid, "offset": 1},
                 {**valid, "limit": 2}, {**valid, "limit": False},
                 {**valid, "units": "pch"}, {**valid, "output_type": 2},
                 {**valid, "output_type": True}, {**valid, "output_type": "1"},
                 {**valid, "observations": [None] * 3},
                 {**valid, "observations": [{"date": "2026-07-01"}] * 3})
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    read_observations(payload, SERIES[0])

    def test_banxico_rejects_wrong_series_errors_and_missing_fields(self):
        cases = ({"bmx": []}, {"bmx": {"error": "fixture error"}},
                 {"bmx": {"series": []}},
                 {"bmx": {"series": [{"idSerie": "OTHER", "datos": []}]}},
                 {"bmx": {"series": [{"idSerie": "SF43718"}]}},
                 observations_payload(SERIES[3], [{"fecha": "01/09/2026"}]))
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    read_observations(payload, SERIES[3])

    def test_mapping_leaves_native_payload_and_text_precision_unchanged(self):
        for series in (SERIES[0], SERIES[3]):
            with self.subTest(provider=series["provider"]):
                payload = observations_payload(series)
                before = deepcopy(payload)
                rows = read_observations(payload, series)
                self.assertEqual(payload, before)
                # Cambiar la copia de trabajo tampoco modifica los registros nativos.
                rows[0]["value"] = "changed in the test"
                self.assertEqual(payload, before)
