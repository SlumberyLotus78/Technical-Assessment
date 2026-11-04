"""Registro del catálogo público sin reinterpretar series ya almacenadas."""

import psycopg
from psycopg.types.json import Jsonb

from grain_pipeline.sources.catalog import SERIES


def verify_catalog(connection: psycopg.Connection) -> int:
    """Exige las cuatro definiciones completas del catálogo de esta etapa."""
    rows = connection.execute(
        """SELECT provider, series_code, name, unit, frequency, source_title, expected_metadata
           FROM core.series ORDER BY provider, series_code"""
    ).fetchall()
    expected = sorted((series["provider"], series["code"], series["name"], series["unit"],
                       series["frequency"], series["source_title"], series["expected_metadata"])
                      for series in SERIES)
    if rows != expected:
        raise RuntimeError("El catálogo PostgreSQL no coincide con las cuatro series del proyecto.")
    return len(rows)


def prepare_catalog(connection: psycopg.Connection) -> int:
    """Inserta definiciones ausentes y verifica las existentes antes de confirmar."""
    with connection.cursor() as cursor:
        for series in SERIES:
            cursor.execute(
                """INSERT INTO core.series
                   (provider, series_code, name, unit, frequency, source_title, expected_metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (provider, series_code) DO NOTHING""",
                (series["provider"], series["code"], series["name"], series["unit"],
                 series["frequency"], series["source_title"], Jsonb(series["expected_metadata"])),
            )
    return verify_catalog(connection)
