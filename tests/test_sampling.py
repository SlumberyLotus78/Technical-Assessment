"""Planificación de una muestra con metadatos y fechas de referencia ficticios."""

from datetime import date
import unittest

from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.sampling import sample_window, select_sample_month
from tests.fixtures import metadata_entries


class SampleWindowTests(unittest.TestCase):
    def test_provider_windows_have_the_same_final_month(self):
        month = date(2026, 9, 1)
        self.assertEqual(sample_window(SERIES[0], month), (date(2026, 7, 1), date(2026, 9, 30)))
        self.assertEqual(sample_window(SERIES[3], month), (date(2026, 9, 1), date(2026, 9, 30)))
        # Los argumentos de mes deben representar su primer día.
        with self.assertRaises(ValueError):
            sample_window(SERIES[0], date(2026, 9, 15))

    def test_oldest_latest_declared_month_limits_the_sample(self):
        entries = metadata_entries()
        # Una de las series mensuales termina antes que las otras dos.
        entries[1]["metadata"]["observation_end"] = "2026-08-01"
        self.assertEqual(select_sample_month(entries, date(2026, 11, 3)), date(2026, 8, 1))

    def test_current_open_month_is_excluded(self):
        entries = metadata_entries()
        for entry in entries:
            if entry["series"]["provider"] == "FRED":
                entry["metadata"]["observation_end"] = "2026-11-01"
            else:
                entry["metadata"]["fechaFin"] = "03/11/2026"
        self.assertEqual(select_sample_month(entries, date(2026, 11, 3)), date(2026, 10, 1))

    def test_january_reference_uses_previous_december(self):
        entries = metadata_entries()
        for entry in entries:
            if entry["series"]["provider"] == "FRED":
                entry["metadata"]["observation_end"] = "2026-01-01"
            else:
                entry["metadata"]["fechaFin"] = "15/01/2026"
        self.assertEqual(select_sample_month(entries, date(2026, 1, 15)), date(2025, 12, 1))

    def test_requested_available_month_is_honored(self):
        selected = select_sample_month(metadata_entries(), date(2026, 11, 3), date(2026, 6, 1))
        self.assertEqual(selected, date(2026, 6, 1))

    def test_requested_open_unavailable_or_noninitial_month_is_rejected(self):
        # Noviembre está abierto; octubre supera los datos mensuales del ejemplo;
        # septiembre 15 no es un identificador válido de mes.
        for requested in (date(2026, 11, 1), date(2026, 10, 1), date(2026, 9, 15)):
            with self.subTest(requested=requested):
                with self.assertRaises(ValueError):
                    select_sample_month(metadata_entries(), date(2026, 11, 3), requested)

    def test_incomplete_or_duplicate_series_are_rejected(self):
        entries = metadata_entries()
        for invalid in (entries[:-1], entries + entries[:1]):
            with self.subTest(size=len(invalid)):
                with self.assertRaises(ValueError):
                    select_sample_month(invalid, date(2026, 11, 3))

    def test_insufficient_history_for_proposed_window_is_rejected(self):
        for index, field, value in ((0, "observation_start", "2026-08-01"),
                                    (3, "fechaInicio", "15/09/2026")):
            with self.subTest(index=index):
                entries = metadata_entries()
                entries[index]["metadata"][field] = value
                with self.assertRaises(ValueError):
                    select_sample_month(entries, date(2026, 11, 3))

    def test_daily_last_date_can_precede_calendar_month_end(self):
        # El 31 de octubre de 2026 es sábado. El fin declarado en viernes
        # permite proponer octubre para inspección; su cobertura se evaluará después.
        entries = metadata_entries()
        for entry in entries[:3]:
            entry["metadata"]["observation_end"] = "2026-10-01"
        self.assertEqual(select_sample_month(entries, date(2026, 11, 3)), date(2026, 10, 1))
