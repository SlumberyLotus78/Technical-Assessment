"""Escenarios ficticios para las reglas de metadatos, sin comunicación HTTP."""

import unittest

from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.contracts import validate_metadata
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
