"""Pruebas del transporte HTTP con sesiones y respuestas simuladas."""

import unittest
from unittest.mock import Mock

import requests

from grain_pipeline.clients.http import BASE_URLS, TIMEOUT, request_json


# Credenciales ficticias: permiten comprobar dónde se colocan los valores.
CREDENTIALS = {"FRED_API_KEY": "fixture-fred-key", "BANXICO_TOKEN": "fixture-banxico-token"}


def make_session(payload=None, status=200, content_type="application/json"):
    """Prepara los objetos simulados que necesita el escenario."""
    # Mock registra las llamadas y permite definir sus resultados.
    response = Mock()
    response.status_code = status
    response.headers = {"Content-Type": content_type}
    response.json.return_value = {} if payload is None else payload
    # spec limita los nombres disponibles a los de una Session de requests.
    session = Mock(spec=requests.Session)
    # Cuando el cliente llame a get, recibirá nuestra respuesta simulada.
    session.get.return_value = response
    return session, response


class HttpClientTests(unittest.TestCase):
    """Comprobaciones del cliente real con comunicación externa simulada."""

    def test_fred_authentication_and_connection_options(self):
        payload = {"seriess": [{"id": "PMAIZMTUSDM"}]}
        session, response = make_session(payload, content_type="application/json; charset=utf-8")
        params = {"series_id": "PMAIZMTUSDM", "file_type": "json"}

        result = request_json(session, "FRED", "series", params, CREDENTIALS)

        self.assertEqual(result, payload)
        # Verificamos los argumentos exactos entregados a la sesión simulada.
        session.get.assert_called_once_with(
            BASE_URLS["FRED"] + "series",
            params={**params, "api_key": CREDENTIALS["FRED_API_KEY"]},
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
            allow_redirects=False,
        )
        self.assertNotIn("api_key", params)
        response.close.assert_called_once()

    def test_banxico_token_uses_header(self):
        session, response = make_session({"bmx": {"series": []}})

        request_json(session, "Banxico", "series/SF43718", {"locale": "es"}, CREDENTIALS)

        session.get.assert_called_once_with(
            BASE_URLS["Banxico"] + "series/SF43718",
            params={"locale": "es"},
            headers={"Accept": "application/json", "Bmx-Token": CREDENTIALS["BANXICO_TOKEN"]},
            timeout=TIMEOUT,
            allow_redirects=False,
        )
        response.close.assert_called_once()

    def test_http_errors_release_response_and_exclude_private_body(self):
        # subTest permite recorrer variantes conservando su identificación si fallan.
        for status in (302, 400, 401, 403, 429, 503):
            with self.subTest(status=status):
                session, response = make_session({"error": CREDENTIALS["FRED_API_KEY"]}, status=status)
                with self.assertRaises(RuntimeError) as error:
                    request_json(session, "FRED", "series", {}, CREDENTIALS)

                self.assertIn(str(status), str(error.exception))
                self.assertNotIn(CREDENTIALS["FRED_API_KEY"], str(error.exception))
                session.get.assert_called_once()
                response.json.assert_not_called()
                response.close.assert_called_once()

    def test_connection_errors_exclude_original_exception_details(self):
        for error_type in (requests.Timeout, requests.ConnectionError):
            with self.subTest(error_type=error_type.__name__):
                session, _ = make_session()
                # side_effect hace que la llamada simulada lance una excepción.
                session.get.side_effect = error_type("fixture URL with " + CREDENTIALS["FRED_API_KEY"])
                with self.assertRaises(RuntimeError) as error:
                    request_json(session, "FRED", "series", {}, CREDENTIALS)

                self.assertNotIn(CREDENTIALS["FRED_API_KEY"], str(error.exception))
                self.assertTrue(error.exception.__suppress_context__)

    def test_invalid_response_formats_are_rejected(self):
        cases = (
            ("text/html", {}, None),
            ("application/json", {}, ValueError(CREDENTIALS["FRED_API_KEY"])),
            ("application/json", [], None),
        )
        for content_type, payload, json_error in cases:
            with self.subTest(content_type=content_type, payload_type=type(payload).__name__):
                session, response = make_session(payload, content_type=content_type)
                if json_error is not None:
                    response.json.side_effect = json_error
                with self.assertRaises(RuntimeError) as error:
                    request_json(session, "FRED", "series", {}, CREDENTIALS)

                self.assertNotIn(CREDENTIALS["FRED_API_KEY"], str(error.exception))
                response.close.assert_called_once()

    def test_invalid_destinations_and_private_parameters_are_rejected(self):
        cases = (
            ("Other", "series", {}),
            ("FRED", "https://other.example/series", {}),
            ("FRED", "../series", {}),
            ("FRED", "series", {"api_key": "fixture-key"}),
            ("Banxico", "series/SF43718", {"token": "fixture-token"}),
        )
        for provider, path, params in cases:
            with self.subTest(provider=provider, path=path):
                session, _ = make_session()
                with self.assertRaises(ValueError):
                    request_json(session, provider, path, params, CREDENTIALS)
                session.get.assert_not_called()
