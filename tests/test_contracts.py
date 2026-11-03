"""Escenarios ficticios para las reglas de metadatos, sin comunicación HTTP."""

import unittest

from datetime import date
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.contracts import read_metadata_range, validate_metadata
from tests.fixtures import metadata_payload, metadata_record


class MetadataContractTests(unittest.TestCase):
    """Casos que aceptan o rechazan el contenido según su significado esperado."""

    def test_expected_metadata_is_accepted_for_all_series(self):
        for series in SERIES:
            with self.subTest(code=series["code"]):
                record = metadata_record(series)
                result = validate_metadata(metadata_payload(series, record), series)
                self.assertEqual(result, record)

    def test_text_normalization_preserves_original_values(self):
        for series in SERIES:
            with self.subTest(code=series["code"]):
                record = metadata_record(series)
                title_field = "title" if series["provider"] == "FRED" else "titulo"
                # Preparamos diferencias de presentación en los campos requeridos.
                # list(diccionario) obtiene sus claves; agregamos el campo del título.
                fields = list(series["expected_metadata"]) + [title_field]
                for field in fields:
                    record[field] = "  " + record[field].upper().replace(" ", " \t ") + "  "
                original = dict(record)

                result = validate_metadata(metadata_payload(series, record), series)

                # La comparación debe aceptar la presentación equivalente y
                # devolver los textos originales, conservando espacios y mayúsculas.
                self.assertEqual(result, original)

    def test_wrong_units_are_rejected(self):
        cases = ((SERIES[0], "units", "U.S. Dollars per Bushel"),
                 (SERIES[3], "unidad", "Dólares por Peso"))
        for series, field, value in cases:
            with self.subTest(code=series["code"]):
                record = metadata_record(series)
                record[field] = value
                with self.assertRaises(ValueError):
                    validate_metadata(metadata_payload(series, record), series)

    def test_wrong_frequencies_are_rejected(self):
        cases = ((SERIES[0], "frequency", "Annual"),
                 (SERIES[0], "frequency_short", "Q"),
                 (SERIES[3], "periodicidad", "Mensual"))
        for series, field, value in cases:
            with self.subTest(code=series["code"], field=field):
                record = metadata_record(series)
                record[field] = value
                with self.assertRaises(ValueError):
                    validate_metadata(metadata_payload(series, record), series)

    def test_wrong_titles_are_rejected(self):
        cases = ((SERIES[0], "title", "Global price of Rice"),
                 (SERIES[3], "titulo", "Tipo de cambio - Fecha de liquidación"))
        for series, field, value in cases:
            with self.subTest(code=series["code"]):
                record = metadata_record(series)
                record[field] = value
                with self.assertRaises(ValueError):
                    validate_metadata(metadata_payload(series, record), series)

    def test_missing_required_fields_are_rejected(self):
        # Se elimina un campo por escenario para comprobar que sea obligatorio.
        for series in (SERIES[0], SERIES[3]):
            title_field = "title" if series["provider"] == "FRED" else "titulo"
            fields = list(series["expected_metadata"]) + [title_field]
            for field in fields:
                with self.subTest(code=series["code"], field=field):
                    record = metadata_record(series)
                    record.pop(field)
                    with self.assertRaises(ValueError):
                        validate_metadata(metadata_payload(series, record), series)

    def test_non_text_required_fields_are_rejected(self):
        for series, field in ((SERIES[0], "units"), (SERIES[3], "titulo")):
            for value in (None, 42, True):
                with self.subTest(code=series["code"], field=field, value=value):
                    record = metadata_record(series)
                    record[field] = value
                    with self.assertRaises(ValueError):
                        validate_metadata(metadata_payload(series, record), series)

    def test_wrong_classification_is_rejected(self):
        # La unidad y la frecuencia pueden ser correctas y aun así cambiar
        # la clasificación estacional de FRED o el tipo de cifra de Banxico.
        cases = ((SERIES[0], "seasonal_adjustment_short", "SA"),
                 (SERIES[3], "cifra", "Porcentaje"))
        for series, field, value in cases:
            with self.subTest(code=series["code"], field=field):
                record = metadata_record(series)
                record[field] = value
                with self.assertRaises(ValueError):
                    validate_metadata(metadata_payload(series, record), series)

    def test_date_ranges_are_read_for_both_providers(self):
        self.assertEqual(read_metadata_range(metadata_record(SERIES[0]), SERIES[0]),
                         (date(2010, 1, 1), date(2026, 9, 1)))
        self.assertEqual(read_metadata_range(metadata_record(SERIES[3]), SERIES[3]),
                         (date(2010, 1, 1), date(2026, 10, 30)))

    def test_missing_or_invalid_date_values_are_rejected(self):
        cases = ((SERIES[0], "observation_end", None),
                 (SERIES[0], "observation_end", "2026-02-29"),
                 (SERIES[3], "fechaFin", "2026-10-30"),
                 (SERIES[3], "fechaInicio", "31/02/2026"))
        for series, field, value in cases:
            with self.subTest(code=series["code"], field=field, value=value):
                record = metadata_record(series)
                record[field] = value
                with self.assertRaises(ValueError):
                    validate_metadata(metadata_payload(series, record), series)

    def test_reversed_date_ranges_are_rejected(self):
        cases = ((SERIES[0], "observation_start", "2026-10-01"),
                 (SERIES[3], "fechaInicio", "01/11/2026"))
        for series, field, value in cases:
            with self.subTest(code=series["code"]):
                record = metadata_record(series)
                record[field] = value
                with self.assertRaises(ValueError):
                    validate_metadata(metadata_payload(series, record), series)

    def test_monthly_range_dates_must_identify_month_start(self):
        for field, value in (("observation_start", "2010-01-02"),
                             ("observation_end", "2026-09-15")):
            with self.subTest(field=field):
                record = metadata_record(SERIES[0])
                record[field] = value
                with self.assertRaises(ValueError):
                    validate_metadata(metadata_payload(SERIES[0], record), SERIES[0])
