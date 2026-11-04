"""Bloqueo de sesión del producto, sus transacciones las controla el coordinador."""

import psycopg

from grain_pipeline.persistence.runs import require_transactional_connection


# Es distinto del bloqueo transaccional (746238, 1) del instalador SQL.
PRODUCT_LOCK = (746238, 2)


def acquire_product_lock(connection: psycopg.Connection) -> bool:
    """Intenta adquirir el bloqueo sin esperar, sobrevive a commit y rollback."""
    require_transactional_connection(connection)
    return connection.execute("SELECT pg_try_advisory_lock(%s, %s)", PRODUCT_LOCK).fetchone()[0]


def release_product_lock(connection: psycopg.Connection) -> None:
    """Libera exactamente una adquisición del bloqueo de esta sesión."""
    released = connection.execute("SELECT pg_advisory_unlock(%s, %s)", PRODUCT_LOCK).fetchone()[0]
    if not released:
        raise RuntimeError("La sesión no tenía adquirido el bloqueo del producto.")
