"""Comando: python -m grain_pipeline.persistence.initialize --env-file .env."""

import argparse
from pathlib import Path
import sys

import psycopg

from grain_pipeline.common.config import load_database_url
from grain_pipeline.persistence.catalog import prepare_catalog, verify_catalog
from grain_pipeline.persistence.database import database_error_message, open_connection
from grain_pipeline.persistence.schema import MODEL_TABLES, SCHEMA_VERSION, apply_schema, verify_schema


def main(argv=None) -> int:
    """Prepara o comprueba el esquema en la base indicada explícitamente."""
    parser = argparse.ArgumentParser(description="Prepara el modelo PostgreSQL y su catálogo.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--check-only", action="store_true",
                        help="Comprueba versión, tablas y catálogo en una transacción de solo lectura.")
    args = parser.parse_args(argv)
    try:
        database_url = load_database_url(args.env_file)
        with open_connection(database_url) as connection:
            if args.check_only:
                connection.read_only = True
                verify_schema(connection)
                series_count = verify_catalog(connection)
                created = False
            else:
                created = apply_schema(connection)
                series_count = prepare_catalog(connection)
    except psycopg.Error as error:
        print(database_error_message(error), file=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except OSError:
        print("No se pudo leer la configuración o el recurso SQL del paquete.", file=sys.stderr)
        return 1

    action = "comprobado" if args.check_only else ("creado" if created else "verificado")
    print("PostgreSQL | conexión comprobada")
    print(f"Esquema {action} | versión: {SCHEMA_VERSION}")
    print(f"Tablas del modelo: {len(MODEL_TABLES)} | tabla de versiones SQL: 1")
    print(f"Catálogo comprobado: {series_count} series.")
    print("Comprobación finalizada." if args.check_only else "Preparación PostgreSQL finalizada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
