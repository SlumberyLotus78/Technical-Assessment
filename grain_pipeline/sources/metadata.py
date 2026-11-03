"""Consulta  de metadatos e identificación de las cuatro series.
"""

import argparse
from pathlib import Path
import sys

import requests

from grain_pipeline.clients.http import request_json
from grain_pipeline.common.config import load_credentials
from grain_pipeline.sources.catalog import SERIES


def fetch_metadata(session: requests.Session, series: dict, credentials: dict) -> dict:
    """Consulta una serie y comprueba que el identificador recibido sea el esperado."""
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

    payload = request_json(session, provider, path, params, credentials)
    if any(name in payload for name in ("error", "error_code", "error_message")):
        raise ValueError(f"{provider} {code}: la fuente devolvió un error.")

    if provider == "FRED":
        records = payload.get("seriess")
        identifier_field = "id"
    else:
        bmx = payload.get("bmx")
        records = bmx.get("series") if isinstance(bmx, dict) and "error" not in bmx else None
        identifier_field = "idSerie"

    # Consultamos una sola serie por petición, por lo que esperamos un registro.
    if not isinstance(records, list) or len(records) != 1:
        raise ValueError(f"{provider} {code}: estructura de metadatos inesperada.")
    record = records[0]
    if not isinstance(record, dict) or record.get(identifier_field) != code:
        raise ValueError(f"{provider} {code}: identificador recibido incompatible.")
    return record


def main(argv=None) -> int:
    """Coordina el diagnóstico solicitado desde la terminal."""
    parser = argparse.ArgumentParser(description="Consulta metadatos de FRED y Banxico.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args(argv)

    try:
        credentials = load_credentials(args.env_file)
        with requests.Session() as session:
            for series in SERIES:
                fetch_metadata(session, series, credentials)
                print(f"{series['provider']} | {series['code']} | metadatos recibidos e identificador comprobado")
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1

    print(f"Comprobación finalizada: {len(SERIES)} series.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
