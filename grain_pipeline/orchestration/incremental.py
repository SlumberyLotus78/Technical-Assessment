"""Incremental independiente: plan por watermark, revisión reciente y publicación Gold."""

import argparse
from datetime import date, datetime
import logging
from pathlib import Path
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
from grain_pipeline.orchestration.incremental_plan import plan_incremental_window
from grain_pipeline.orchestration.locking import product_publication_lock
from grain_pipeline.orchestration.publication import publish_registered_captures
from grain_pipeline.persistence.catalog import verify_catalog
from grain_pipeline.persistence.database import database_error_message, open_connection
from grain_pipeline.persistence.quality import record_quality_result
from grain_pipeline.persistence.runs import begin_run, set_run_period, set_run_stage
from grain_pipeline.persistence.schema import verify_schema
from grain_pipeline.persistence.watermarks import complete_skipped_incremental, read_watermark
from grain_pipeline.quality.incremental import DEFAULT_REVIEW_MONTHS, validate_incremental_baseline, validate_review_months
from grain_pipeline.quality.windows import validate_source_availability
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.windows import yearly_query_windows


LOGGER = logging.getLogger(__name__)


def run_incremental(connection: psycopg.Connection, session: requests.Session, credentials: dict,
                     bronze_root: Path, *, as_of: date, review_months: int = DEFAULT_REVIEW_MONTHS,
                     end_month: date | None = None) -> dict:
    """Actualiza un producto inicializado; nunca invoca el coordinador histórico."""
    validate_review_months(review_months)
    with product_publication_lock(connection):
        verify_schema(connection)
        verify_catalog(connection)
        run_id = begin_run(connection, "incremental")
        connection.commit()
        stage, step = "planning", "baseline"
        first, last = None, None
        directory = bronze_root / "incremental" / str(run_id)
        try:
            previous = read_watermark(connection)
            validate_incremental_baseline(previous, as_of=as_of)
            # Este alcance permite registrar un fallo de planificación aunque
            # todavía no se conozca la ventana de observaciones a consultar.
            first, last = previous["start_month"], previous["published_through_month"]
            directory.mkdir(parents=True)
            connection.commit()
            step = "metadata"
            metadata = collect_metadata(connection, session, credentials, run_id, bronze_root, directory)
            capture_ids = metadata["capture_ids"]
            step = "planning"
            plan = plan_incremental_window(previous, metadata["entries"], as_of=as_of,
                                           review_months=review_months, end_month=end_month)
            windows = yearly_query_windows(plan["start_month"], plan["end_month"]) if plan["has_work"] else []
            write_json(directory / "query_plan.json", {
                "run_id": str(run_id), "load_type": "incremental", "as_of": as_of.isoformat(),
                "watermark_before": previous["published_through_month"].isoformat(),
                "latest_common_month": plan["latest_common_month"].isoformat(), "review_months": review_months,
                "end_month_cap": end_month.isoformat() if end_month is not None else None,
                "start_month": plan["start_month"].isoformat() if plan["has_work"] else None,
                "end_month": plan["end_month"].isoformat() if plan["has_work"] else None,
                "metadata_requests": len(SERIES), "observation_requests": len(windows) * len(SERIES),
                "windows": [{"start": start.isoformat(), "end": end.isoformat()} for start, end in windows]})

            if not plan["has_work"]:
                # Omitir consultas de observaciones también exige que la fuente
                # siga declarando el último mes certificado y que las capas
                # publicadas correspondan a sus capturas originales.
                step = "availability"
                validate_source_availability(metadata["entries"], last, last, as_of=as_of)
                write_capture_manifest(connection, run_id, capture_ids, bronze_root, directory)
                step = "baseline"
                for code in ("CTL-01", "CTL-02", "CTL-04"):
                    record_quality_result(connection, run_id, rule_code=code, status="passed",
                                          details={"decision": "no_new_months_in_selected_range", "review_months": 0,
                                                   "latest_common_month": plan["latest_common_month"].isoformat(),
                                                   "end_month_cap": end_month.isoformat() if end_month is not None else None},
                                          period_start=first, period_end=month_end(last))
                complete_skipped_incremental(connection, run_id, previous, bronze_root, as_of=as_of)
                connection.commit()
                empty = {"received": 0, "written": 0, "unchanged": 0}
                result = {"run_id": str(run_id), "status": "skipped", "silver": dict(empty),
                          "gold": {"fx_monthly": dict(empty), "grain_reference_monthly": dict(empty)},
                          "watermark_after": previous["published_through_month"].isoformat()}
            else:
                first, last = plan["start_month"], plan["end_month"]
                set_run_period(connection, run_id, first, last)
                connection.commit()
                step = "availability"
                validate_source_availability(metadata["entries"], first, last, as_of=as_of)
                stage, step = "extraction", "observations"
                set_run_stage(connection, run_id, stage)
                connection.commit()
                capture_ids.extend(collect_observation_windows(connection, session, credentials, run_id,
                                                               bronze_root, directory, first, last))
                stage = "quality"
                set_run_stage(connection, run_id, stage)
                captures = write_capture_manifest(connection, run_id, capture_ids, bronze_root, directory)
                write_window_profile(run_id, captures, first, last, directory, "incoming_profile.json")
                # El publicador integra esta ventana con Silver y reconstruye
                # Gold completo para preservar comparadores MoM y YoY exactos.
                result = publish_registered_captures(connection, run_id, capture_ids, bronze_root, as_of=as_of)
                result.update(status="succeeded", watermark_after=result["end_month"])
        except Exception as error:
            record_attempt_failure(connection, run_id, stage, step, error, start=first, end=last)
            LOGGER.error("Incremental interrumpido | ejecución: %s | consultar ops.runs y ops.dq_results", run_id)
            raise

        result.update(watermark_before=previous["published_through_month"].isoformat(), review_months=review_months,
                      latest_common_month=plan["latest_common_month"].isoformat(),
                      end_month_cap=end_month.isoformat() if end_month is not None else None,
                      request_start_month=plan["start_month"].isoformat() if plan["has_work"] else None,
                      request_end_month=plan["end_month"].isoformat() if plan["has_work"] else None,
                      bronze_directory=directory.relative_to(bronze_root).as_posix())
        write_run_result(directory, result, filename="run_result.json")
        return result


def main(argv=None) -> int:
    """Comando incremental con corte opcional y solapamiento explícito, independiente del histórico."""
    parser = argparse.ArgumentParser(description="Actualiza un histórico publicado y reconstruye Gold.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--bronze-root", type=Path, default=Path("data/bronze"))
    parser.add_argument("--review-months", type=int, default=DEFAULT_REVIEW_MONTHS,
                        help="Meses publicados a revisar, entre 0 y 12; predeterminado: 3.")
    parser.add_argument("--end-month", type=parse_month, help="Tope cerrado opcional, YYYY-MM.")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        validate_review_months(args.review_months)
        as_of = datetime.now(ZoneInfo(OPERATING_TIMEZONE)).date()
        credentials = load_credentials(args.env_file)
        database_url = load_database_url(args.env_file)
        with open_connection(database_url) as connection, requests.Session() as session:
            result = run_incremental(connection, session, credentials, args.bronze_root, as_of=as_of,
                                     review_months=args.review_months, end_month=args.end_month)
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
        print("No se pudo leer la configuración o conservar la actualización local.", file=sys.stderr)
        return 1
    print(f"Incremental | ejecución: {result['run_id']} | estado: {result['status']}")
    print(f"Watermark | {result['watermark_before']} a {result['watermark_after']}")
    print(f"Silver | recibidas: {result['silver']['received']} | escritas: {result['silver']['written']}")
    print(f"Gold | FIX escritos: {result['gold']['fx_monthly']['written']} | referencias escritas: {result['gold']['grain_reference_monthly']['written']}")
    print(f"Bronze: {args.bronze_root / result['bronze_directory']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
