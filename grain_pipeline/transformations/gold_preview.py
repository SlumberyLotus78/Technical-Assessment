"""Comando de vista previa Gold desde Bronze; no abre conexiones ni carga .env."""

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from grain_pipeline.common.dates import OPERATING_TIMEZONE, month_end, parse_month
from grain_pipeline.common.decimal_policy import DECIMAL_PRECISION, DECIMAL_ROUNDING
from grain_pipeline.extraction.capture_reader import read_capture
from grain_pipeline.extraction.raw import write_json
from grain_pipeline.quality.calendar import check_fix_coverage
from grain_pipeline.sources.catalog import SERIES, get_series
from grain_pipeline.sources.observations import read_observations
from grain_pipeline.transformations.gold import build_monthly_gold
from grain_pipeline.transformations.silver import latest_complete_sample, prepare_observations


def prepare_gold_preview(directory: Path, bronze_root: Path, month: date, *, as_of: date) -> dict:
    """Prepara un mes de muestra y conserva los hashes de sus cuatro entradas."""
    captures = [read_capture(path, bronze_root) for path in sorted(directory.glob("*_observations.json"))]
    expected = {(series["provider"], series["code"]) for series in SERIES}
    received = [(capture["provider"], capture["series_code"]) for capture in captures]
    if set(received) != expected or len(received) != len(expected):
        raise ValueError("La vista previa requiere una captura de observaciones por cada serie.")
    selected, sources = [], []
    for capture in captures:
        if (capture["kind"] != "observations" or capture["window_start"] > month
                or capture["window_end"] < month_end(month)):
            raise ValueError("Las capturas deben cubrir todo el mes elegido para Gold.")
        series = get_series(capture["provider"], capture["series_code"])
        native = read_observations(capture["payload"], series)
        # Primero se valida toda la captura, después se selecciona el mes.
        # Así una fila rota fuera del mes no se oculta mediante un filtro previo.
        prepared = prepare_observations(native, series, capture["window_start"], capture["window_end"])
        selected.extend(row for row in prepared if row["observation_date"].replace(day=1) == month)
        sources.append({"provider": capture["provider"], "series_code": capture["series_code"],
                        "storage_path": capture["storage_path"], "content_sha256": capture["content_sha256"]})

    gold = build_monthly_gold(selected, month, month, as_of=as_of)
    fix = [row for row in selected if row["provider"] == "Banxico"]
    # El informe es JSON público: DATE -> ISO, Decimal -> texto sin pérdida de dígitos.
    exported = {table: [{key: value.isoformat() if type(value) is date else
                        str(value) if isinstance(value, Decimal) else value for key, value in row.items()}
                       for row in rows] for table, rows in gold.items()}
    return {"verified_at_utc": datetime.now(timezone.utc).isoformat(), "as_of": as_of.isoformat(),
            "month": month.isoformat(), "sample_directory": directory.name, "source_captures": sources,
            "selected_silver_rows": len(selected), "database_written": False,
            "decimal_precision": DECIMAL_PRECISION, "decimal_rounding": DECIMAL_ROUNDING,
            "coverage_check": check_fix_coverage(fix, month), **exported}


def main(argv=None) -> int:
    """Muestra referencias y, opcionalmente, crea un informe sin sobrescribir archivos."""
    parser = argparse.ArgumentParser(description="Vista previa Gold de un mes cerrado desde archivos locales.")
    parser.add_argument("--month", required=True, help="Mes explícito en formato YYYY-MM.")
    parser.add_argument("--bronze-root", type=Path, default=Path("data/bronze"))
    parser.add_argument("--sample-dir", type=Path, help="Por defecto se usa la última muestra completa.")
    parser.add_argument("--output", type=Path, help="Informe JSON nuevo; se rechaza un archivo existente.")
    args = parser.parse_args(argv)
    try:
        month = parse_month(args.month)
        directory = args.sample_dir if args.sample_dir is not None else latest_complete_sample(args.bronze_root)
        as_of = datetime.now(ZoneInfo(OPERATING_TIMEZONE)).date()
        report = prepare_gold_preview(directory, args.bronze_root, month, as_of=as_of)
        if args.output is not None:
            write_json(args.output, report)
    except (ValueError, OSError) as error:
        message = str(error) if isinstance(error, ValueError) else "No se pudo leer la muestra o crear el informe nuevo."
        print(message, file=sys.stderr)
        return 1
    fx = report["fx_monthly"][0]
    print(f"Mes: {args.month}")
    print(f"DQ-09 passed | fechas FIX: {fx['observed_days']}/{fx['expected_days']}")
    print(f"FIX promedio MXN/USD: {fx['average_fix']}")
    for row in report["grain_reference_monthly"]:
        print(f"{row['series_code']} | referencia MXN/t: {row['reference_mxn_t']}")
    print("MoM y YoY: sin comparadores dentro de esta vista previa de un mes.")
    print("Vista previa Gold finalizada: 3 referencias; sin escritura en PostgreSQL.")
    if args.output is not None:
        print(f"Informe creado: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
