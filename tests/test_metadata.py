"""Pruebas de selección e identidad de series con respuestas ficticias."""

import unittest
from unittest.mock import Mock, patch

from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.metadata import fetch_metadata
from tests.fixtures import metadata_payload, metadata_record


CREDENTIALS = {"FRED_API_KEY": "fixture-fred-key", "BANXICO_TOKEN": "fixture-banxico-token"}


class MetadataTests(unittest.TestCase):
    """Comprueba la función de metadatos independientemente del transporte."""

    def test_fred_endpoint_and_identifier(self):
        series = SERIES[0]
        session = Mock()
        # El registro ficticio ahora incluye los campos exigidos por el contrato.
        record = metadata_record(series)
        # Sustituimos la referencia a request_json que utiliza este módulo.
        # La función fetch_metadata sigue ejecutándose realmente.
        with patch("grain_pipeline.sources.metadata.request_json",
                   return_value=metadata_payload(series, record)) as request:
            result = fetch_metadata(session, series, CREDENTIALS)

        self.assertEqual(result, record)
        request.assert_called_once_with(session, "FRED", "series",
                                        {"series_id": series["code"], "file_type": "json"}, CREDENTIALS)

    def test_banxico_endpoint_and_identifier(self):
        series = SERIES[3]
        session = Mock()
        record = metadata_record(series)
        with patch("grain_pipeline.sources.metadata.request_json",
                   return_value=metadata_payload(series, record)) as request:
            result = fetch_metadata(session, series, CREDENTIALS)

        self.assertEqual(result, record)
        request.assert_called_once_with(session, "Banxico", f"series/{series['code']}",
                                        {"locale": "es"}, CREDENTIALS)

    def test_wrong_identifiers_errors_and_shapes_are_rejected(self):
        # Cada tupla contiene la serie consultada y una respuesta incompatible.
        cases = (
            (SERIES[0], {"seriess": [{"id": "OTHER"}]}),
            (SERIES[0], {"seriess": []}),
            (SERIES[0], {"seriess": ["unexpected text"]}),
            (SERIES[0], {"error_code": 400, "error_message": "fixture error"}),
            (SERIES[3], {"bmx": {"series": [{"idSerie": "OTHER"}]}}),
            (SERIES[3], {"bmx": []}),
            (SERIES[3], {"bmx": {"error": "fixture error"}}),
        )
        for series, payload in cases:
            with self.subTest(code=series["code"], payload=payload):
                with patch("grain_pipeline.sources.metadata.request_json", return_value=payload):
                    with self.assertRaises(ValueError):
                        fetch_metadata(Mock(), series, CREDENTIALS)
