"""Reglas numéricas con ejemplos ficticios; no se consultan fuentes reales."""

from decimal import Decimal
import unittest

from grain_pipeline.quality.values import parse_source_value


class SourceValueTests(unittest.TestCase):
    """Distingue valores ausentes, formatos incompatibles y números válidos."""

    def test_decimal_preserves_all_digits_from_the_source_text(self):
        value = "100.1234567890123456789"
        self.assertEqual(str(parse_source_value(value, "FRED")), value)

    def test_banxico_grouping_requires_complete_thousands_groups(self):
        self.assertEqual(parse_source_value("1,234,567.8900", "Banxico"), Decimal("1234567.8900"))
        self.assertEqual(parse_source_value(" 18.1234 ", "Banxico"), Decimal("18.1234"))
        for value in ("18,75", "1,23,456.00", "1,000,00", "1.234,56"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_source_value(value, "Banxico")

    def test_missing_markers_are_distinct_from_zero(self):
        cases = (("FRED", None), ("FRED", "."), ("FRED", " "),
                 ("Banxico", None), ("Banxico", "N/E"), ("Banxico", "N/D"), ("Banxico", ""))
        for provider, value in cases:
            with self.subTest(provider=provider, value=value):
                self.assertIsNone(parse_source_value(value, provider))
        self.assertEqual(parse_source_value("0", "FRED"), Decimal("0"))

    def test_invalid_types_formats_and_non_finite_text_are_rejected(self):
        for value in (12.34, 12, True, {}, "NaN", "Infinity", "-Infinity",
                      "1_000.00", "1e3", "1,234.56", "N/E", "unknown"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_source_value(value, "FRED")
        with self.assertRaises(ValueError):
            parse_source_value("1", "Other")

    def test_zero_and_negative_numbers_remain_visible_for_the_positivity_rule(self):
        # El parser conserva los números. El perfil aplica la regla de positividad.
        self.assertEqual(parse_source_value("-2.50", "FRED"), Decimal("-2.50"))
        self.assertEqual(parse_source_value("+0.00", "Banxico"), Decimal("0.00"))
