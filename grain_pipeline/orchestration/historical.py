"""Carga histórica inicial explícita: extracción, perfil y publicación hasta Gold."""

import argparse
from datetime import date, datetime, timezone
import logging
from pathlib import Path
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg
import requests

from grain_pipeline.common.config import load_credentials, load_database_url
from grain_pipeline.common.dates import OPERATING_TIMEZONE, month_end, parse_month
from grain_pipeline.extraction.history import capture_historical_metadata, capture_historical_observations
from grain_pipeline.extraction.raw import write_json
from grain_pipeline.orchestration.locking import product_publication_lock
from grain_pipeline.orchestration.profiling import profile_historical_captures
from grain_pipeline.orchestration.publication import publish_registered_captures
from grain_pipeline.persistence.captures import read_registered_capture, register_capture
from grain_pipeline.persistence.catalog import verify_catalog
from grain_pipeline.persistence.database import database_error_message, open_connection
from grain_pipeline.persistence.quality import record_quality_result
from grain_pipeline.persistence.runs import begin_run, fail_run, get_run_status, set_run_stage
from grain_pipeline.persistence.schema import verify_schema
from grain_pipeline.persistence.watermarks import read_watermark
from grain_pipeline.quality.history import validate_historical_availability, validate_historical_period
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.contracts import validate_metadata_record
from grain_pipeline.sources.observations import read_observations
from grain_pipeline.sources.windows import yearly_query_windows


LOGGER = logging.getLogger(__name__)


def run_historical(connection: psycopg.Connection, session: requests.Session, credentials: dict,
                    bronze_root: Path, start: date, end: date, *, as_of: date) -> dict:
    """Inicializa un producto sin watermark, el incremental tendrá otro coordinador."""
    validate_historical_period(start, end, as_of=as_of)
    with product_publication_lock(connection):
        verify_schema(connection)
        verify_catalog(connection)
        run_id = begin_run(connection, "historical", start, end)
        connection.commit()
        stage, source_step = "planning", "initialization"
        capture_ids, entries = [], []
        directory = bronze_root / "historical" / str(run_id)
        try:
            if read_watermark(connection) is not None:
                raise ValueError("La base ya tiene un histórico publicado, este comando realiza la inicialización.")
            directory.mkdir(parents=True)
            stage, source_step = "extraction", "metadata"
            set_run_stage(connection, run_id, stage)
            connection.commit()
            for series in SERIES:
                LOGGER.info("Metadatos | %s | %s", series["provider"], series["code"])
                path = capture_historical_metadata(session, series, credentials, directory)
                capture_id = register_capture(connection, run_id, path, bronze_root)
                connection.commit()  # La captura queda registrada incluso si su contrato falla.
                capture = read_registered_capture(connection, capture_id, bronze_root)
                record = validate_metadata_record(capture["payload"], series)
                capture_ids.append(capture_id)
                entries.append({"series": series, "metadata": record})
                connection.commit()  # No se mantiene una transacción abierta durante la próxima petición.

            source_step = "availability"
            validate_historical_availability(entries, start, end, as_of=as_of)
            windows = yearly_query_windows(start, end)
            write_json(directory / "query_plan.json", {
                "run_id": str(run_id), "load_type": "historical", "as_of": as_of.isoformat(),
                "start_month": start.isoformat(), "end_month": end.isoformat(),
                "metadata_requests": len(SERIES), "observation_requests": len(windows) * len(SERIES),
                "windows": [{"start": first.isoformat(), "end": last.isoformat()} for first, last in windows]})
            source_step = "observations"
            for series in SERIES:
                for first, last in windows:
                    LOGGER.info("Observaciones | %s | %s | %s a %s", series["provider"], series["code"], first, last)
                    path = capture_historical_observations(session, series, credentials, directory, first, last)
                    capture_id = register_capture(connection, run_id, path, bronze_root)
                    connection.commit()
                    capture = read_registered_capture(connection, capture_id, bronze_root)
                    # La respuesta se conserva antes del contrato. Un error estructural detiene las consultas posteriores de este intento.
                    read_observations(capture["payload"], series)
                    capture_ids.append(capture_id)
                    connection.commit()

            stage = "quality"
            set_run_stage(connection, run_id, stage)
            captures = [read_registered_capture(connection, capture_id, bronze_root) for capture_id in capture_ids]
            connection.commit()
            write_json(directory / "extraction_manifest.json", {
                "run_id": str(run_id), "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                "captures": [{"capture_id": str(capture_id), "provider": capture["provider"],
                              "series_code": capture["series_code"], "kind": capture["kind"],
                              "storage_path": capture["storage_path"], "sha256": capture["content_sha256"]}
                             for capture_id, capture in zip(capture_ids, captures)]})
            profile = profile_historical_captures(captures, start, end)
            write_json(directory / "historical_profile.json", {"run_id": str(run_id), **profile})
            # El publicador repite las verificaciones contra los archivos
            # registrados y conserva sus resultados SQL antes de escribir hechos.
            result = publish_registered_captures(connection, run_id, capture_ids, bronze_root, as_of=as_of)
        except Exception as error:
            if connection.closed or connection.broken:
                raise
            connection.rollback()
            if get_run_status(connection, run_id) == "running":
                rules = {"initialization": "CTL-01", "availability": "CTL-02", "metadata": "SRC-02", "observations": "SRC-03"}
                code = "PUB-01" if stage == "quality" else rules[source_step]
                record_quality_result(connection, run_id, rule_code=code, status="failed",
                                      details={"stage": stage, "step": source_step, "error_type": type(error).__name__},
                                      period_start=start, period_end=month_end(end))
                fail_run(connection, run_id, stage, error)
                connection.commit()
            else:
                connection.rollback()  # El publicador ya registró el cierre del intento.
            LOGGER.error("Histórico interrumpido | ejecución: %s | consultar ops.runs y ops.dq_results", run_id)
            raise

        result["bronze_directory"] = directory.relative_to(bronze_root).as_posix()
        try:
            write_json(directory / "publication_result.json", result)
        except OSError:
            # El commit ya ocurrió. Un fallo al exportar el resumen local
            # no convierte una publicación confirmada en un intento fallido.
            LOGGER.warning("Publicación confirmada | no se pudo crear el resumen local | ejecución: %s", run_id)
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
        validate_historical_period(args.start_month, args.end_month, as_of=as_of)
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
