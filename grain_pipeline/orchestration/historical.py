"""Carga histórica inicial explícita: extracción, perfil y publicación hasta Gold."""

import argparse
from datetime import date, datetime
import logging
from pathlib import Path
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg
import requests

from grain_pipeline.common.config import load_credentials, load_database_url
from grain_pipeline.common.dates import OPERATING_TIMEZONE, parse_month
from grain_pipeline.extraction.raw import write_json
from grain_pipeline.orchestration.artifacts import write_capture_manifest, write_run_result, write_window_profile
from grain_pipeline.orchestration.extraction import collect_metadata, collect_observation_windows
from grain_pipeline.orchestration.failures import record_attempt_failure
from grain_pipeline.orchestration.locking import product_publication_lock
from grain_pipeline.orchestration.publication import publish_registered_captures
from grain_pipeline.persistence.catalog import verify_catalog
from grain_pipeline.persistence.database import database_error_message, open_connection
from grain_pipeline.persistence.runs import begin_run, set_run_stage
from grain_pipeline.persistence.schema import verify_schema
from grain_pipeline.persistence.watermarks import read_watermark
from grain_pipeline.quality.windows import validate_closed_period, validate_source_availability
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.windows import yearly_query_windows


LOGGER = logging.getLogger(__name__)


def run_historical(connection: psycopg.Connection, session: requests.Session, credentials: dict,
                    bronze_root: Path, start: date, end: date, *, as_of: date) -> dict:
    """Inicializa un producto sin watermark, el incremental tendrá otro coordinador."""
    validate_closed_period(start, end, as_of=as_of)
    with product_publication_lock(connection):
        verify_schema(connection)
        verify_catalog(connection)
        run_id = begin_run(connection, "historical", start, end)
        connection.commit()
        stage, source_step = "planning", "initialization"
        directory = bronze_root / "historical" / str(run_id)
        try:
            if read_watermark(connection) is not None:
                raise ValueError("La base ya tiene un histórico publicado; este comando realiza la inicialización.")
            directory.mkdir(parents=True)
            stage, source_step = "extraction", "metadata"
            set_run_stage(connection, run_id, stage)
            connection.commit()
            metadata = collect_metadata(connection, session, credentials, run_id, bronze_root, directory)
            capture_ids = metadata["capture_ids"]
            source_step = "availability"
            validate_source_availability(metadata["entries"], start, end, as_of=as_of)
            windows = yearly_query_windows(start, end)
            write_json(directory / "query_plan.json", {
                "run_id": str(run_id), "load_type": "historical", "as_of": as_of.isoformat(),
                "start_month": start.isoformat(), "end_month": end.isoformat(),
                "metadata_requests": len(SERIES), "observation_requests": len(windows) * len(SERIES),
                "windows": [{"start": first.isoformat(), "end": last.isoformat()} for first, last in windows]})
            source_step = "observations"
            capture_ids.extend(collect_observation_windows(connection, session, credentials, run_id,
                                                           bronze_root, directory, start, end))

            stage = "quality"
            set_run_stage(connection, run_id, stage)
            captures = write_capture_manifest(connection, run_id, capture_ids, bronze_root, directory)
            write_window_profile(run_id, captures, start, end, directory, "historical_profile.json")
            # El publicador repite las verificaciones contra los archivos
            # registrados y conserva sus resultados SQL antes de escribir hechos.
            result = publish_registered_captures(connection, run_id, capture_ids, bronze_root, as_of=as_of)
        except Exception as error:
            record_attempt_failure(connection, run_id, stage, source_step, error, start=start, end=end)
            LOGGER.error("Histórico interrumpido | ejecución: %s | consultar ops.runs y ops.dq_results", run_id)
            raise

        result["bronze_directory"] = directory.relative_to(bronze_root).as_posix()
        write_run_result(directory, result)
        return result


def main(argv=None) -> int:
    """Comando histórico separado: exige periodo, configuración privada y base preparada."""
    parser = argparse.ArgumentParser(description="Carga histórica inicial de FRED y Banxico hasta Gold.")
    parser.add_argument("--start-month", required=True, type=parse_month, help="Primer mes, YYYY-MM.")
    parser.add_argument("--end-month", required=True, type=parse_month, help="Último mes cerrado, YYYY-MM.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--bronze-root", type=Path, default=Path("data/bronze"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        as_of = datetime.now(ZoneInfo(OPERATING_TIMEZONE)).date()
        validate_closed_period(args.start_month, args.end_month, as_of=as_of)
        credentials = load_credentials(args.env_file)
        database_url = load_database_url(args.env_file)
        with open_connection(database_url) as connection, requests.Session() as session:
            result = run_historical(connection, session, credentials, args.bronze_root,
                                    args.start_month, args.end_month, as_of=as_of)
    except ZoneInfoNotFoundError:
        print("Faltan datos de zona horaria; instala requirements.txt.", file=sys.stderr)
        return 1
    except psycopg.Error as error:
        print(database_error_message(error), file=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except OSError:
        print("No se pudo leer la configuración o conservar la extracción histórica local.", file=sys.stderr)
        return 1
    print(f"Histórico publicado | ejecución: {result['run_id']}")
    print(f"Silver | recibidas: {result['silver']['received']} | escritas: {result['silver']['written']}")
    print(f"Gold | meses FIX: {result['gold']['fx_monthly']['received']} | referencias: {result['gold']['grain_reference_monthly']['received']}")
    print(f"Bronze: {args.bronze_root / result['bronze_directory']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
