"""Reintentos con transporte y esperas simulados; nunca realiza llamadas externas."""

from datetime import datetime, timezone
import unittest
from unittest.mock import Mock, call, patch

import requests

from grain_pipeline.clients.http import request_json
from grain_pipeline.clients.retry import retry_delay
from tests.historical_fixtures import CREDENTIALS, json_response


class RetryPolicyTests(unittest.TestCase):
    """La política respeta Retry-After y mantiene los intentos y esperas acotados."""

    def test_delay_accepts_seconds_dates_and_invalid_headers_without_shortening_server_wait(self):
        now = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
        self.assertEqual(retry_delay(1), 1)
        self.assertEqual(retry_delay(2, "bad"), 2)
        self.assertEqual(retry_delay(1, "0000000002"), 2)
        self.assertEqual(retry_delay(1, "Tue, 03 Nov 2026 12:00:03 GMT", now=now), 3)
        self.assertEqual(retry_delay(1, "Tue, 03 Nov 2026 11:59:00 GMT", now=now), 0)
        self.assertIsNone(retry_delay(1, "31"))
        self.assertIsNone(retry_delay(1, "Tue, 03 Nov 2026 12:01:00 GMT", now=now))

    def test_retryable_response_is_closed_before_waiting_and_then_can_succeed(self):
        session = Mock(spec=requests.Session)
        first, second = json_response({}, status=503), json_response({"ok": True})
        session.get.side_effect = [first, second]
        with patch("grain_pipeline.clients.http.time.sleep") as sleep:
            sleep.side_effect = lambda _: first.close.assert_called_once()
            self.assertEqual(request_json(session, "FRED", "series", {}, CREDENTIALS), {"ok": True})
        self.assertEqual(session.get.call_count, 2)
        second.close.assert_called_once()

    def test_429_honors_retry_after_and_excessive_wait_stops_without_an_early_retry(self):
        for header, expected_calls in (("2", 2), ("60", 1)):
            session = Mock(spec=requests.Session)
            session.get.side_effect = [json_response({}, status=429, headers={"Retry-After": header}), json_response({})]
            with patch("grain_pipeline.clients.http.time.sleep") as sleep:
                if expected_calls == 1:
                    with self.assertRaises(RuntimeError):
                        request_json(session, "FRED", "series", {}, CREDENTIALS)
                    sleep.assert_not_called()
                else:
                    request_json(session, "FRED", "series", {}, CREDENTIALS)
                    sleep.assert_called_once_with(2)
            self.assertEqual(session.get.call_count, expected_calls)

    def test_transient_connection_failure_can_recover_and_exhaustion_is_private(self):
        session = Mock(spec=requests.Session)
        session.get.side_effect = [requests.Timeout(CREDENTIALS["FRED_API_KEY"]), json_response({})]
        with patch("grain_pipeline.clients.http.time.sleep"):
            self.assertEqual(request_json(session, "FRED", "series", {}, CREDENTIALS), {})
        session.get.reset_mock()
        session.get.side_effect = requests.ConnectionError(CREDENTIALS["FRED_API_KEY"])
        with patch("grain_pipeline.clients.http.time.sleep") as sleep, self.assertRaises(RuntimeError) as caught:
            request_json(session, "FRED", "series", {}, CREDENTIALS)
        self.assertEqual(session.get.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(1), call(2)])
        self.assertNotIn(CREDENTIALS["FRED_API_KEY"], str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_authentication_tls_and_semantic_errors_are_not_retried(self):
        for response in (json_response({}, status=401), json_response({}, status=404), json_response([])):
            session = Mock(spec=requests.Session)
            session.get.return_value = response
            with patch("grain_pipeline.clients.http.time.sleep") as sleep, self.assertRaises(RuntimeError):
                request_json(session, "FRED", "series", {}, CREDENTIALS)
            session.get.assert_called_once()
            sleep.assert_not_called()
        session.get.reset_mock()
        session.get.side_effect = requests.exceptions.SSLError("fixture")
        with self.assertRaises(RuntimeError):
            request_json(session, "FRED", "series", {}, CREDENTIALS)
        session.get.assert_called_once()

    def test_invalid_attempt_counts_never_open_a_request(self):
        session = Mock(spec=requests.Session)
        for attempts in (0, 4, True, "3"):
            with self.subTest(attempts=attempts), self.assertRaises(ValueError):
                request_json(session, "FRED", "series", {}, CREDENTIALS, max_attempts=attempts)
        session.get.assert_not_called()
