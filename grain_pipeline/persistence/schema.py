"""Instalación inicial versionada, sin reemplazar objetos de otros modelos."""

from hashlib import sha256
from importlib.resources import files

import psycopg


SCHEMA_VERSION = "001_initial"
MODEL_TABLES = {
    ("core", "series"), ("core", "observations"),
    ("ops", "runs"), ("ops", "raw_captures"), ("ops", "dq_results"), ("ops", "watermarks"),
    ("mart", "fx_monthly"), ("mart", "grain_reference_monthly"),
}
MIGRATION_TABLE = ("ops", "schema_migrations")
# Dos identificadores estables reservan el bloqueo de preparación de este
# proyecto. El bloqueo se libera al confirmar o revertir la transacción.
SCHEMA_LOCK = (746238, 1)


def schema_resource() -> tuple[str, str]:
    """Lee el SQL del paquete y calcula el hash de su contenido normalizado."""
    resource = files("grain_pipeline.persistence.sql").joinpath(f"{SCHEMA_VERSION}.sql")
    # Normalizamos saltos para que el checkout CRLF de Windows y un wheel con
    # LF identifiquen el mismo SQL. El contenido lógico no depende del equipo.
    content = resource.read_text(encoding="utf-8").replace("\r\n", "\n")
    return content, sha256(content.encode("utf-8")).hexdigest()


def _migration_exists(connection: psycopg.Connection) -> bool:
    """Pregunta por la tabla de versiones sin crear objetos."""
    row = connection.execute("SELECT to_regclass('ops.schema_migrations')").fetchone()
    return row[0] is not None


def _check_empty_schemas(connection: psycopg.Connection) -> None:
    """Rechaza objetos previos cuando no existe el registro de esta instalación."""
    # pg_class incluye tablas, vistas, índices y secuencias. Un esquema vacío
    # creado desde pgAdmin sí es compatible con la preparación inicial.
    rows = connection.execute(
        """SELECT c.relname FROM pg_catalog.pg_class AS c
           JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
           WHERE n.nspname IN ('core', 'mart', 'ops') LIMIT 1"""
    ).fetchall()
    if rows:
        raise RuntimeError("Los esquemas core, mart u ops contienen objetos sin esta versión. "
                           "Utiliza una base del proyecto compatible o una base nueva.")


def verify_schema(connection: psycopg.Connection) -> None:
    """Comprueba versión, checksum y presencia de las nueve tablas esperadas."""
    if not _migration_exists(connection):
        raise RuntimeError("La base aún no tiene el esquema del proyecto preparado.")
    _, checksum = schema_resource()
    rows = connection.execute(
        "SELECT version, checksum FROM ops.schema_migrations ORDER BY version"
    ).fetchall()
    if rows != [(SCHEMA_VERSION, checksum)]:
        raise RuntimeError("La versión SQL instalada no coincide con el código de esta etapa.")
    tables = connection.execute(
        """SELECT schemaname, tablename FROM pg_catalog.pg_tables
           WHERE schemaname IN ('core', 'mart', 'ops')"""
    ).fetchall()
    if set(tables) != MODEL_TABLES | {MIGRATION_TABLE}:
        raise RuntimeError("Las tablas instaladas no coinciden con la versión SQL registrada.")


def apply_schema(connection: psycopg.Connection) -> bool:
    """Instala una vez; verifica una instalación existente y devuelve si hubo creación."""
    # Este es un bloqueo de instalación, separado del futuro bloqueo de cargas.
    # El llamador confirmará SQL, versión y catálogo en la misma transacción.
    # Una sesión que retenga un bloqueo no dejará esperando indefinidamente.
    connection.execute("SET LOCAL lock_timeout = '10s'")
    connection.execute("SELECT pg_advisory_xact_lock(%s, %s)", SCHEMA_LOCK)
    if _migration_exists(connection):
        verify_schema(connection)
        return False

    _check_empty_schemas(connection)
    content, checksum = schema_resource()
    # El SQL es un recurso fijo del repositorio. Los valores variables se
    # entregan como parámetros, nunca concatenados al texto de las consultas.
    connection.execute(content, prepare=False)
    connection.execute(
        "INSERT INTO ops.schema_migrations (version, checksum) VALUES (%s, %s)",
        (SCHEMA_VERSION, checksum),
    )
    verify_schema(connection)
    return True
