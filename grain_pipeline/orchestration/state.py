"""Comprobación de solo lectura del producto y sus originales antes de automatizar."""

import argparse
from datetime import date, datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg

from grain_pipeline.common.config import load_database_url
from grain_pipeline.common.dates import OPERATING_TIMEZONE
from grain_pipeline.extraction.raw import write_json
from grain_pipeline.persistence.catalog import verify_catalog
from grain_pipeline.persistence.database import database_error_message, open_connection
from grain_pipeline.persistence.gold import read_monthly_gold, read_silver_observations
from grain_pipeline.persistence.schema import verify_schema
from grain_pipeline.persistence.watermarks import read_watermark
from grain_pipeline.quality.incremental import validate_incremental_baseline
from grain_pipeline.quality.publication import validate_stored_gold
from grain_pipeline.transformations.gold import build_monthly_gold


def check_published_state(connection: psycopg.Connection, bronze_root: Path, *, as_of: date) -> dict:
    """No crea intentos ni actualiza el avance; verifica el histórico que exige el incremental."""
    verify_schema(connection)
    verify_catalog(connection)
    previous = read_watermark(connection, for_update=False)
    validate_incremental_baseline(previous, as_of=as_of)
    first, last = previous["start_month"], previous["published_through_month"]
    records = read_silver_observations(connection, first, last, bronze_root)
    expected = build_monthly_gold(records, first, last, as_of=as_of)
    validate_stored_gold(expected, read_monthly_gold(connection, first, last))
    return {"ready": True, "start_month": first.isoformat(), "published_through_month": last.isoformat(),
            "initial_run_id": str(previous["initial_run_id"]), "last_run_id": str(previous["last_run_id"]),
            "silver_rows": len(records), "fx_months": len(expected["fx_monthly"]),
            "grain_references": len(expected["grain_reference_monthly"])}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Comprueba el estado publicado sin modificar la base ni consultar APIs.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--bronze-root", type=Path, default=Path("data/bronze"))
    parser.add_argument("--report", type=Path, help="Informe JSON nuevo; la carpeta debe existir.")
    args = parser.parse_args(argv)
    try:
        as_of = datetime.now(ZoneInfo(OPERATING_TIMEZONE)).date()
        with open_connection(load_database_url(args.env_file)) as connection:
            connection.read_only = True
            connection.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
            result = check_published_state(connection, args.bronze_root, as_of=as_of)
        if args.report is not None:
            write_json(args.report, result)
    except ZoneInfoNotFoundError:
        print("Faltan datos de zona horaria; instala las dependencias del paquete.", file=sys.stderr)
        return 1
    except psycopg.Error as error:
        print(database_error_message(error), file=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except OSError:
        print("No se pudo comprobar la configuración, Bronze o el informe de estado.", file=sys.stderr)
        return 1
    print(f"Estado listo para incremental | {result['start_month']} a {result['published_through_month']}")
    print(f"Silver: {result['silver_rows']} | FIX mensuales: {result['fx_months']} | referencias: {result['grain_references']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
