"""Preparación Silver y vista previa local de las capturas de muestra."""

import argparse
from datetime import date
import json
from pathlib import Path
import sys

from grain_pipeline.common.dates import parse_date
from grain_pipeline.extraction.capture_reader import read_capture
from grain_pipeline.quality.observations import validate_observations
from grain_pipeline.quality.values import parse_source_value
from grain_pipeline.sources.catalog import SERIES, get_series
from grain_pipeline.sources.observations import read_observations


def prepare_observations(records: list[dict], series: dict, start: date, end: date) -> list[dict]:
    """Devuelve fechas y Decimal sin redondear, tras aprobar las reglas de registros."""
    validate_observations(records, series, start, end)
    prepared = [{"provider": series["provider"], "series_code": series["code"],
                 "observation_date": parse_date(row["date"], iso=series["provider"] == "FRED"),
                 "value": parse_source_value(row["value"], series["provider"])} for row in records]
    # El orden común facilita reproducir resultados y escribir las claves en el mismo orden cuando otra ejecución revisa un intervalo anterior.
    return sorted(prepared, key=lambda row: row["observation_date"])


def latest_complete_sample(bronze_root: Path) -> Path:
    """Elige la última carpeta de muestras con un perfil final completo."""
    root = bronze_root.resolve()
    samples = bronze_root / "samples"
    if samples.is_dir():
        for directory in sorted(samples.iterdir(), reverse=True):
            profile_path = directory / "profile.json"
            if directory.is_dir() and profile_path.is_file():
                if not profile_path.resolve().is_relative_to(root):
                    continue
                try:
                    report = json.loads(profile_path.read_text(encoding="utf-8-sig"))
                except (ValueError, UnicodeError):
                    continue
                if isinstance(report, dict) and report.get("status") == "completed":
                    return directory
    raise ValueError("No se encontró una muestra completa dentro de Bronze.")


def main(argv=None) -> int:
    """Muestra la preparación de registros desde archivos, sin publicar una carga."""
    parser = argparse.ArgumentParser(description="Vista previa de observaciones preparadas para Silver.")
    parser.add_argument("--bronze-root", type=Path, default=Path("data/bronze"))
    parser.add_argument("--sample-dir", type=Path, help="Muestra explícita; por defecto usa la última completa.")
    args = parser.parse_args(argv)
    try:
        directory = args.sample_dir if args.sample_dir is not None else latest_complete_sample(args.bronze_root)
        captures = [read_capture(path, args.bronze_root)
                    for path in sorted(directory.glob("*_observations.json"))]
        expected = {(series["provider"], series["code"]) for series in SERIES}
        received = [(capture["provider"], capture["series_code"]) for capture in captures]
        if set(received) != expected or len(received) != len(expected):
            raise ValueError("La vista previa requiere una captura de observaciones por cada serie.")
        prepared_by_series = []
        for capture in captures:
            if capture["kind"] != "observations":
                raise ValueError("Tipo de captura incompatible con la vista previa Silver.")
            series = get_series(capture["provider"], capture["series_code"])
            records = read_observations(capture["payload"], series)
            prepared_by_series.append((series, prepare_observations(
                records, series, capture["window_start"], capture["window_end"])))
    except (ValueError, OSError) as error:
        # Los mensajes propios excluyen contenido privado; los errores de
        # archivo se resumen para mantener el mismo criterio en el comando.
        message = str(error) if isinstance(error, ValueError) else "No se pudo leer la muestra local."
        print(message, file=sys.stderr)
        return 1

    print(f"Muestra: {directory}")
    for series, rows in prepared_by_series:
        print(f"{series['provider']} | {series['code']} | registros preparados: {len(rows)}")
    print("Cobertura FIX para publicación: pendiente de calendario bancario.")
    print(f"Vista previa Silver finalizada: {sum(len(rows) for _, rows in prepared_by_series)} observaciones.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
