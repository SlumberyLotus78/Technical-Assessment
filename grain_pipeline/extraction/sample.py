"""Descarga y perfil de una muestra: python -m grain_pipeline.extraction.sample."""

import argparse
from datetime import date, datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from grain_pipeline.common.config import load_credentials
from grain_pipeline.common.dates import OPERATING_TIMEZONE, parse_month
from grain_pipeline.extraction.raw import create_sample_directory, save_capture, write_json
from grain_pipeline.quality.profiling import profile_observations
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.metadata import fetch_metadata
from grain_pipeline.sources.observations import fetch_observations, read_observations
from grain_pipeline.sources.sampling import sample_window, select_sample_month


def collect_sample(session: requests.Session, credentials: dict, directory: Path,
                   today: date, requested: date | None = None) -> dict:
    """Coordina consultas, capturas y perfiles utilizando las funciones compartidas."""
    entries = []
    for series in SERIES:
        record = fetch_metadata(session, series, credentials)
        # fetch_metadata devuelve el registro validado, con sus textos originales.
        save_capture(directory, series, "metadata", record)
        entries.append({"series": series, "metadata": record})

    selected = select_sample_month(entries, today, requested)
    profiles = []
    for entry in entries:
        series = entry["series"]
        start, end = sample_window(series, selected)
        payload = fetch_observations(session, series, start, end, credentials)
        # Guardamos el JSON de observaciones ANTES del contrato y las reglas.
        # Una respuesta incompatible queda disponible para revisar su estructura.
        save_capture(directory, series, "observations", payload, start, end)
        records = read_observations(payload, series)
        profiles.append(profile_observations(records, series, start, end))

    report = {
        # completed indica que terminó el diagnóstico; has_issues expresa el resultado de sus reglas. Esto no publica Silver, Gold ni watermarks.
        "status": "completed",
        "reference_date": today.isoformat(),
        "sample_month": selected.strftime("%Y-%m"),
        "has_issues": any(profile["has_issues"] for profile in profiles),
        "profiles": profiles,
    }

    # Solo una ejecución que alcanzó las cuatro series escribe el perfil final.
    # Si una consulta o un contrato fallan, las capturas previas permanecen.
    write_json(directory / "profile.json", report)
    return report


def main(argv=None) -> int:
    """Interpreta opciones y devuelve un código de salida para la terminal."""
    parser = argparse.ArgumentParser(description="Descarga y perfila una muestra de FRED y Banxico.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--month", type=parse_month, help="Mes final opcional, YYYY-MM.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/bronze/samples"),
                        help="Carpeta raíz para las capturas de muestra.")
    args = parser.parse_args(argv)

    try:
        credentials = load_credentials(args.env_file)
        today = datetime.now(ZoneInfo(OPERATING_TIMEZONE)).date()
        directory = create_sample_directory(args.output_dir)
        print(f"Carpeta de esta ejecución: {directory}")
        with requests.Session() as session:
            report = collect_sample(session, credentials, directory, today, args.month)
    except ZoneInfoNotFoundError:
        print("Faltan datos de zona horaria; instala requirements.txt.", file=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as error:
        print(f"Diagnóstico incompleto: {error}", file=sys.stderr)
        return 1
    except OSError:
        # El detalle de rutas del sistema no aporta al diagnóstico de las fuentes.
        print("No se pudo leer la configuración o guardar la muestra local.", file=sys.stderr)
        return 1

    print(f"Mes de muestra: {report['sample_month']}")
    for profile in report["profiles"]:
        result = "incidencias detectadas" if profile["has_issues"] else "sin incidencias en las reglas actuales"
        print(f"{profile['provider']} | {profile['series_code']} | "
              f"registros: {profile['rows']} | {result}")
    print("Cobertura diaria FIX: pendiente de comprobar con el calendario bancario.")
    print(f"Perfil guardado: {directory / 'profile.json'}")
    if report["has_issues"]:
        print("Muestra inspeccionada con incidencias; revisar profile.json.", file=sys.stderr)
        return 1
    print(f"Muestra descargada e inspeccionada: {len(SERIES)} series.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
