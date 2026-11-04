"""Ámbito de exclusión del producto, reutilizable por las futuras cargas."""

from contextlib import contextmanager

import psycopg
from psycopg.pq import TransactionStatus

from grain_pipeline.persistence.locking import acquire_product_lock, release_product_lock
from grain_pipeline.persistence.runs import require_transactional_connection


@contextmanager
def product_publication_lock(connection: psycopg.Connection):
    """Usa una conexión dedicada y sin trabajo pendiente"""
    require_transactional_connection(connection)
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError("La coordinación requiere una conexión sin transacción pendiente.")
    acquired = acquire_product_lock(connection)
    connection.commit()  # Solo confirma la consulta que intentó obtener el bloqueo.
    if not acquired:
        raise RuntimeError("El producto tiene otra ejecución en curso; no se inició la publicación.")
    try:
        yield
    finally:
        # El coordinador ya confirmó sus fases. Ante una excepción, cualquier transacción aún abierta se revierte antes de liberar la sesión.
        if not connection.closed and not connection.broken:
            connection.rollback()
            release_product_lock(connection)
            connection.commit()
