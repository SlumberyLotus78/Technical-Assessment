"""Agregación, referencias y variaciones con datos ficticios y capturas archivadas."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, Inexact, ROUND_DOWN, localcontext
import io
import json
from pathlib import Path
import tempfile
import unittest

from grain_pipeline.common.dates import months_between, shift_month
from grain_pipeline.sources.banking_calendar import banking_calendar_for_month
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.transformations.gold import add_reference_changes, build_monthly_gold
from grain_pipeline.transformations.gold_preview import main, prepare_gold_preview
from grain_pipeline.transformations.monthly_fx import aggregate_monthly_fix
from tests.fixtures import FIX_SAMPLE_MONTH as MONTH, september_fix


AS_OF = date(2026, 11, 3)
ARCHIVE = Path(__file__).resolve().parents[1] / "docs/evidencias/perfilamiento_inicial"


def gold_inputs() -> list[dict]:
    """Tres precios ficticios y 21 FIX ficticios con media conocida: 17.0011."""
    grains = [{"provider": series["provider"], "series_code": series["code"],
               "observation_date": MONTH, "value": Decimal((position + 1) * 100)}
              for position, series in enumerate(SERIES[:3])]
    fix = [{**row, "value": Decimal("17") + Decimal(position + 1) / Decimal("10000")}
           for position, row in enumerate(september_fix())]
    return grains + fix


class GoldCalculationTests(unittest.TestCase):
    """Los resultados usan el FIX medio calculado y mantienen los valores de entrada."""

    def test_known_mean_and_references_use_decimal_and_preserve_input(self):
        rows = gold_inputs()
        original = deepcopy(rows)
        result = build_monthly_gold(rows, MONTH, MONTH, as_of=AS_OF)
        self.assertEqual(result, build_monthly_gold(rows[::-1], MONTH, MONTH, as_of=AS_OF))
        fx = result["fx_monthly"][0]
        self.assertEqual(fx["average_fix"], Decimal("17.0011"))
        self.assertEqual(fx["observed_days"], fx["expected_days"])
        for row in result["grain_reference_monthly"]:
            self.assertEqual(row["reference_mxn_t"], row["grain_price_usd_t"] * Decimal("17.0011"))
            self.assertEqual(row["average_fix_mxn_usd"], fx["average_fix"])
            self.assertIsNone(row["mom_change_pct"])
            self.assertIsNone(row["yoy_change_pct"])
        self.assertEqual(rows, original)

    def test_calculations_ignore_and_restore_the_callers_decimal_context(self):
        rows = gold_inputs()
        expected = build_monthly_gold(rows, MONTH, MONTH, as_of=AS_OF)
        with localcontext() as context:
            context.prec, context.rounding = 5, ROUND_DOWN
            context.traps[Inexact] = True
            flags = context.flags.copy()
            self.assertEqual(build_monthly_gold(rows, MONTH, MONTH, as_of=AS_OF), expected)
            self.assertEqual((context.prec, context.rounding), (5, ROUND_DOWN))
            self.assertEqual(context.flags, flags)

    def test_missing_grain_duplicate_and_invalid_silver_inputs_block_gold(self):
        rows = gold_inputs()
        cases = (rows[1:], rows + [rows[0]], [{**rows[0], "value": 100.0}, *rows[1:]],
                 [{**rows[0], "value": Decimal("NaN")}, *rows[1:]],
                 [{**rows[0], "observation_date": datetime(2026, 9, 1)}, *rows[1:]],
                 [{**rows[0], "observation_date": date(2026, 9, 2)}, *rows[1:]],
                 [{**rows[0], "observation_date": date(2026, 8, 1)}, *rows[1:]],
                 [{**rows[0], "series_code": "other"}, *rows[1:]], [{}], [])
        for records in cases:
            with self.subTest(size=len(records)), self.assertRaises(ValueError):
                build_monthly_gold(records, MONTH, MONTH, as_of=AS_OF)

    def test_missing_or_unexpected_fix_and_unreviewed_year_block_gold(self):
        rows = gold_inputs()
        for records in (rows[:-1], rows[:3], rows + [{**rows[3], "observation_date": date(2026, 9, 16)}]):
            with self.subTest(size=len(records)), self.assertRaisesRegex(ValueError, "DQ-09 failed"):
                build_monthly_gold(records, MONTH, MONTH, as_of=AS_OF)
        future = [{**row, "observation_date": date(2027, 1, 1)} for row in rows[:3]]
        with self.assertRaisesRegex(ValueError, "DQ-09 pending"):
            build_monthly_gold(future, date(2027, 1, 1), date(2027, 1, 1), as_of=date(2027, 2, 1))

    def test_current_future_and_invalid_month_windows_are_rejected(self):
        rows = gold_inputs()
        for start, end, as_of in ((MONTH, MONTH, MONTH), (MONTH, MONTH, date(2026, 8, 1)),
                                  (date(2026, 9, 2), MONTH, AS_OF), (MONTH, date(2026, 8, 1), AS_OF)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                build_monthly_gold(rows, start, end, as_of=as_of)

    def test_complete_interval_and_revision_recalculate_dependent_changes(self):
        start = date(2026, 7, 1)
        rows = []
        for month, price in zip(months_between(start, MONTH), ("100", "110", "121")):
            rows.extend({"provider": series["provider"], "series_code": series["code"],
                         "observation_date": month, "value": Decimal(price)} for series in SERIES[:3])
            rows.extend({"provider": "Banxico", "series_code": "SF43718", "observation_date": day,
                         "value": Decimal(20)} for day in banking_calendar_for_month(month)["expected_dates"])
        initial = build_monthly_gold(rows, start, MONTH, as_of=AS_OF)
        self.assertEqual(len(initial["fx_monthly"]), 3)
        self.assertEqual(len(initial["grain_reference_monthly"]), 9)
        corn = [row for row in initial["grain_reference_monthly"] if row["series_code"] == SERIES[0]["code"]]
        self.assertEqual(corn[1]["mom_change_pct"], Decimal(10))
        self.assertEqual(corn[2]["mom_change_pct"], Decimal(10))

        # Revisión ficticia de agosto: cambia su referencia y la variación de septiembre.
        revised = [{**row, "value": Decimal(100)} if row["provider"] == "FRED"
                   and row["observation_date"] == date(2026, 8, 1) else row for row in rows]
        result = build_monthly_gold(revised, start, MONTH, as_of=AS_OF)
        corn = [row for row in result["grain_reference_monthly"] if row["series_code"] == SERIES[0]["code"]]
        self.assertEqual(corn[1]["mom_change_pct"], Decimal(0))
        self.assertEqual(corn[2]["mom_change_pct"], Decimal(21))
        missing_middle_grain = [row for row in rows if not (row["series_code"] == SERIES[0]["code"]
                                                          and row["observation_date"] == date(2026, 8, 1))]
        with self.assertRaises(ValueError):
            build_monthly_gold(missing_middle_grain, start, MONTH, as_of=AS_OF)

    def test_half_even_precision_and_numeric_extremes_are_controlled(self):
        rows = gold_inputs()
        for row in rows[3:]:
            row["value"] = Decimal(1)
        rows[0]["value"] = Decimal("1." + "0" * 33 + "5")
        result = build_monthly_gold(rows, MONTH, MONTH, as_of=AS_OF)
        corn = next(row for row in result["grain_reference_monthly"] if row["series_code"] == SERIES[0]["code"])
        self.assertEqual(corn["reference_mxn_t"], Decimal(1))
        for extreme in ("1e9999999", "1e-9999999"):
            fix = [{**row, "value": Decimal(extreme)} for row in september_fix()]
            with self.subTest(value=extreme), self.assertRaises(ValueError):
                aggregate_monthly_fix(fix, MONTH)


class ReferenceChangesTests(unittest.TestCase):
    """Comparadores exactos y nulos únicamente fuera del intervalo de entrada."""

    def test_mom_and_yoy_use_the_correct_month_and_allow_negative_and_zero(self):
        references = []
        for offset in range(13):
            value = Decimal(1000 if offset == 0 else 1100 if offset == 12 else 2000 if offset == 11 else 1200)
            references.append({"provider": "FRED", "series_code": SERIES[0]["code"],
                               "month": shift_month(date(2025, 1, 1), offset), "reference_mxn_t": value})
        before = deepcopy(references)
        result = add_reference_changes(references[::-1])
        self.assertEqual(result[1]["mom_change_pct"], Decimal(20))
        self.assertEqual(result[2]["mom_change_pct"], Decimal(0))
        self.assertEqual(result[-1]["mom_change_pct"], Decimal(-45))
        self.assertEqual(result[-1]["yoy_change_pct"], Decimal(10))
        self.assertIsNone(result[0]["mom_change_pct"])
        self.assertIsNone(result[11]["yoy_change_pct"])
        self.assertEqual(references, before)

    def test_internal_gaps_and_duplicate_references_are_rejected(self):
        row = {"provider": "FRED", "series_code": SERIES[0]["code"], "month": MONTH,
               "reference_mxn_t": Decimal(1000)}
        for references in ([row, row], [row, {**row, "month": date(2026, 11, 1)}], []):
            with self.subTest(size=len(references)), self.assertRaises(ValueError):
                add_reference_changes(references)

    def test_month_ranges_include_year_boundaries_and_the_maximum_date(self):
        self.assertEqual(months_between(date(2025, 12, 1), date(2026, 1, 1)),
                         [date(2025, 12, 1), date(2026, 1, 1)])
        self.assertEqual(months_between(date(9999, 12, 1), date(9999, 12, 1)), [date(9999, 12, 1)])
        rows = [{"provider": "FRED", "series_code": "test", "month": date(1, month, 1),
                 "reference_mxn_t": Decimal(100)} for month in (1, 2)]
        self.assertEqual(add_reference_changes(rows)[1]["mom_change_pct"], Decimal(0))


class GoldPreviewTests(unittest.TestCase):
    """La muestra real se transforma desde archivos y su informe es reproducible."""

    def test_archived_real_month_has_complete_fix_and_three_references(self):
        manifest = json.loads((ARCHIVE / "manifest.json").read_text(encoding="utf-8"))
        report = prepare_gold_preview(ARCHIVE, ARCHIVE, MONTH, as_of=AS_OF)
        self.assertEqual(report["selected_silver_rows"], 24)
        self.assertFalse(report["database_written"])
        self.assertEqual(report["coverage_check"]["status"], "passed")
        self.assertEqual(len(report["grain_reference_monthly"]), 3)
        self.assertEqual(report["coverage_check"]["details"]["missing_dates"], [])
        # Cada entrada se contrasta con la evidencia original, sin reescribirla.
        hashes = {entry["name"]: entry["sha256"] for entry in manifest["files"]}
        for source in report["source_captures"]:
            self.assertEqual(source["content_sha256"], hashes[source["storage_path"]])
        self.assertEqual(report, json.loads(json.dumps(report)))

    def test_cli_can_export_a_new_report_and_never_overwrites_it(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "preview.json"
            args = ["--month", "2026-09", "--sample-dir", str(ARCHIVE), "--bronze-root", str(ARCHIVE),
                    "--output", str(output)]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 0)
            original = output.read_bytes()
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 1)
            self.assertEqual(output.read_bytes(), original)

    def test_missing_capture_partial_month_and_invalid_cli_month_fail(self):
        # Julio tiene precios en la muestra, pero no una captura FIX de ese mes.
        with self.assertRaises(ValueError):
            prepare_gold_preview(ARCHIVE, ARCHIVE, date(2026, 7, 1), as_of=AS_OF)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                prepare_gold_preview(Path(directory), Path(directory), MONTH, as_of=AS_OF)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--month", "September"]), 1)
