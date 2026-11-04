"""Reconsulta explícita de meses publicados; comparte captura y publicación hasta Gold."""

import argparse
from datetime import date, datetime
from pathlib import Path
import logging
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg
import requests

from grain_pipeline.common.config import load_credentials, load_database_url
from grain_pipeline.common.dates import OPERATING_TIMEZONE, month_end, parse_month
from grain_pipeline.extraction.raw import write_json
from grain_pipeline.orchestration.artifacts import write_capture_manifest, write_run_result, write_window_profile
from grain_pipeline.orchestration.extraction import collect_metadata, collect_observation_windows
from grain_pipeline.orchestration.failures import record_attempt_failure
from grain_pipeline.orchestration.locking import product_publication_lock
from grain_pipeline.orchestration.publication import publish_registered_captures
from grain_pipeline.persistence.catalog import verify_catalog
from grain_pipeline.persistence.database import database_error_message, open_connection
from grain_pipeline.persistence.quality import record_quality_result
from grain_pipeline.persistence.runs import begin_run, set_run_stage
from grain_pipeline.persistence.schema import verify_schema
from grain_pipeline.persistence.watermarks import read_watermark
from grain_pipeline.quality.reprocessing import validate_reprocessing_period
from grain_pipeline.quality.windows import validate_closed_period, validate_source_availability


def run_reprocess(connection: psycopg.Connection, session: requests.Session, credentials: dict,
                  bronze_root: Path, start: date, end: date, *, as_of: date) -> dict:
    """Corrige un intervalo vigente; no modifica el inicio ni el fin del producto."""
    validate_closed_period(start, end, as_of=as_of)
    with product_publication_lock(connection):
        verify_schema(connection)
        verify_catalog(connection)
        # La operación sigue siendo histórica en el modelo existente. CTL-05
        # distingue el reproceso de la inicialización sin alterar el SQL instalado.
        run_id = begin_run(connection, "historical", start, end)
        connection.commit()
        stage, step = "planning", "baseline"
        directory = bronze_root / "reprocess" / str(run_id)
        try:
            previous = read_watermark(connection)
            validate_reprocessing_period(previous, start, end, as_of=as_of)
            record_quality_result(connection, run_id, rule_code="CTL-05", status="passed",
                                  details={"operation": "reprocess", "watermark": previous["published_through_month"].isoformat()},
                                  period_start=start, period_end=month_end(end))
            directory.mkdir(parents=True)
            stage, step = "extraction", "metadata"
            set_run_stage(connection, run_id, stage)
            connection.commit()
            metadata = collect_metadata(connection, session, credentials, run_id, bronze_root, directory)
            step = "availability"
            validate_source_availability(metadata["entries"], start, end, as_of=as_of)
            write_json(directory / "query_plan.json", {"run_id": str(run_id), "operation": "reprocess",
                       "start_month": start.isoformat(), "end_month": end.isoformat(),
                       "published_through_month": previous["published_through_month"].isoformat()})
            step = "observations"
            capture_ids = metadata["capture_ids"] + collect_observation_windows(
                connection, session, credentials, run_id, bronze_root, directory, start, end)
            stage = "quality"
            set_run_stage(connection, run_id, stage)
            captures = write_capture_manifest(connection, run_id, capture_ids, bronze_root, directory)
            write_window_profile(run_id, captures, start, end, directory, "incoming_profile.json")
            result = publish_registered_captures(connection, run_id, capture_ids, bronze_root, as_of=as_of)
        except Exception as error:
            record_attempt_failure(connection, run_id, stage, step, error, start=start, end=end)
            raise
        result.update(operation="reprocess", status="succeeded", bronze_directory=directory.relative_to(bronze_root).as_posix())
        write_run_result(directory, result, filename="run_result.json")
        return result


def main(argv=None) -> int:
    """Comando separado para revisiones fuera de la ventana incremental reciente."""
    parser = argparse.ArgumentParser(description="Reconsulta un intervalo ya publicado y recalcula Gold.")
    parser.add_argument("--start-month", required=True, type=parse_month)
    parser.add_argument("--end-month", required=True, type=parse_month)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--bronze-root", type=Path, default=Path("data/bronze"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        as_of = datetime.now(ZoneInfo(OPERATING_TIMEZONE)).date()
        validate_closed_period(args.start_month, args.end_month, as_of=as_of)
        credentials, database_url = load_credentials(args.env_file), load_database_url(args.env_file)
        with open_connection(database_url) as connection, requests.Session() as session:
            result = run_reprocess(connection, session, credentials, args.bronze_root,
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
        print("No se pudo leer la configuración o conservar el reproceso local.", file=sys.stderr)
        return 1
    print(f"Reproceso | ejecución: {result['run_id']} | estado: succeeded")
    print(f"Silver | escritas: {result['silver']['written']}")
    print(f"Gold | referencias escritas: {result['gold']['grain_reference_monthly']['written']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
