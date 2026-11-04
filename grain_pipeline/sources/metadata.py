"""Consulta pequeña y validación de contratos de metadatos de las cuatro series.
"""

import argparse
from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from grain_pipeline.clients.http import request_json
from grain_pipeline.common.config import load_credentials
from grain_pipeline.common.dates import OPERATING_TIMEZONE, parse_month
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.contracts import read_metadata_range, validate_metadata
from grain_pipeline.sources.sampling import sample_window, select_sample_month


def fetch_metadata(session: requests.Session, series: dict, credentials: dict) -> dict:
    """Consulta una serie y delega en su contrato la validación del contenido."""
    return validate_metadata(fetch_metadata_payload(session, series, credentials), series)


def fetch_metadata_payload(session: requests.Session, series: dict, credentials: dict) -> dict:
    """Obtiene el JSON para conservar una respuesta incompatible antes de validarla."""
    provider = series["provider"]
    code = series["code"]

    if provider == "FRED":
        path = "series"
        params = {"series_id": code, "file_type": "json"}
    elif provider == "Banxico":
        path = f"series/{code}"
        params = {"locale": "es"}
    else:
        raise ValueError("Proveedor de metadatos no soportado.")

    return request_json(session, provider, path, params, credentials)


def main(argv=None) -> int:
    """Coordina el diagnóstico solicitado desde la terminal."""
    parser = argparse.ArgumentParser(description="Consulta metadatos de FRED y Banxico.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--month", type=parse_month, help="Mes final de muestra, YYYY-MM.")
    args = parser.parse_args(argv)

    try:
        credentials = load_credentials(args.env_file)
        # Calculamos la fecha de referencia una vez al iniciar la ejecución.
        today = datetime.now(ZoneInfo(OPERATING_TIMEZONE)).date()
        entries = []
        with requests.Session() as session:
            for series in SERIES:
                record = fetch_metadata(session, series, credentials)
                start, end = read_metadata_range(record, series)
                entries.append({"series": series, "metadata": record})
                # La salida se construye con identificadores públicos del catálogo.
                print(f"{series['provider']} | {series['code']} | metadatos comprobados | "
                      f"disponibilidad declarada: {start.isoformat()} a {end.isoformat()}")

        selected_month = select_sample_month(entries, today, args.month)
        print(f"Fecha de referencia: {today.isoformat()} ({OPERATING_TIMEZONE})")
        print(f"Mes propuesto para muestra: {selected_month.strftime('%Y-%m')}")
        for entry in entries:
            series = entry["series"]
            start, end = sample_window(series, selected_month)
            print(f"{series['provider']} | {series['code']} | muestra propuesta: "
                  f"{start.isoformat()} a {end.isoformat()}")
    except ZoneInfoNotFoundError:
        print("Faltan datos de zona horaria; instala las dependencias de requirements.txt.", file=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as error:
        # Son errores controlados con mensajes que excluyen valores de credenciales.
        print(str(error), file=sys.stderr)
        return 1

    print(f"Plan de muestra preparado: {len(SERIES)} series.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
