"""Ejecución explícita de la suite: python -m tests.run [--postgres --env-file .env]."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import sys
import unittest

from dotenv import dotenv_values
import psycopg
from psycopg.conninfo import conninfo_to_dict

from grain_pipeline.extraction.raw import write_json
from grain_pipeline.persistence.database import database_error_message


def read_test_database_url(env_file: Path) -> str:
    """Lee solo la clave de pruebas; nunca utiliza DATABASE_URL como alternativa."""
    if "TEST_DATABASE_URL" in os.environ:
        value = os.environ["TEST_DATABASE_URL"]
    else:
        value = dotenv_values(env_file, encoding="utf-8-sig", interpolate=False).get("TEST_DATABASE_URL")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Falta TEST_DATABASE_URL para ejecutar las pruebas PostgreSQL.")
    try:
        params = conninfo_to_dict(value.strip())
    except psycopg.Error:
        raise ValueError("TEST_DATABASE_URL tiene un formato incompatible.") from None
    if not params.get("dbname", "").startswith("grain_test_"):
        raise ValueError("TEST_DATABASE_URL requiere una base cuyo nombre comience por grain_test_.")
    return value.strip()


def suite_case_ids(suite):
    """Enumera los casos antes de ejecutarlos; unittest consume la suite al correr."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from suite_case_ids(item)
        else:
            yield item.id()


def main(argv=None) -> int:
    """Carga la conexión solo con --postgres y puede exportar un informe nuevo."""
    parser = argparse.ArgumentParser(description="Pruebas del proyecto, con PostgreSQL opcional y explícito.")
    parser.add_argument("--postgres", action="store_true", help="Exige conexión de prueba y cero omisiones.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--report", type=Path, help="JSON nuevo; su carpeta debe existir.")
    args = parser.parse_args(argv)
    existed = "TEST_DATABASE_URL" in os.environ
    original = os.environ.get("TEST_DATABASE_URL")
    try:
        server_version = None
        if args.postgres:
            os.environ["TEST_DATABASE_URL"] = read_test_database_url(args.env_file)
            with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True, connect_timeout=10) as connection:
                server_version = connection.execute("SHOW server_version").fetchone()[0]
        else:
            os.environ.pop("TEST_DATABASE_URL", None)
        # Debe ocurrir después de configurar el entorno: el soporte SQL lee
        # TEST_DATABASE_URL al importar sus módulos de prueba.
        suite = unittest.defaultTestLoader.discover("tests")
        ids = list(suite_case_ids(suite))
        postgres_ids = {case_id for case_id in ids if case_id.startswith("test_postgres_")}
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        skipped_ids = {case.id() for case, _ in result.skipped}
        successful = result.wasSuccessful() and (not args.postgres or not result.skipped)
        if args.report is not None:
            write_json(args.report, {
                "verified_at_utc": datetime.now(timezone.utc).isoformat(), "python_version": platform.python_version(),
                "postgresql_version": server_version, "postgres_requested": args.postgres,
                "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                "skipped": len(result.skipped), "successful": successful,
                "postgres_tests_executed": len(postgres_ids - skipped_ids),
                "offline_tests_executed": len(set(ids) - postgres_ids - skipped_ids),
                "executed_postgres_cases": sorted(postgres_ids - skipped_ids),
                "project_database_written": False, "api_requests_made": False})
        return 0 if successful else 1
    except psycopg.Error as error:
        print(database_error_message(error), file=sys.stderr)
        return 1
    except (ValueError, OSError) as error:
        message = str(error) if isinstance(error, ValueError) else "No se pudo leer la configuración o crear el informe nuevo."
        print(message, file=sys.stderr)
        return 1
    finally:
        if existed:
            os.environ["TEST_DATABASE_URL"] = original
        else:
            os.environ.pop("TEST_DATABASE_URL", None)


if __name__ == "__main__":
    sys.exit(main())
