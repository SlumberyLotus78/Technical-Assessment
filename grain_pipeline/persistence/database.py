"""Apertura de conexiones PostgreSQL y mensajes que excluyen la conexión privada."""

import psycopg
from psycopg.conninfo import conninfo_to_dict


def database_error_message(error: psycopg.Error) -> str:
    """Resume un error sin imprimir DSN, contraseña, consulta ni detalle original."""
    code = error.sqlstate or "sin SQLSTATE"
    return f"PostgreSQL: {type(error).__name__} ({code})."


def open_connection(database_url: str) -> psycopg.Connection:
    """Conecta a una base explícita y deja el control de transacción al llamador."""
    try:
        params = conninfo_to_dict(database_url)
    except psycopg.Error:
        raise ValueError("DATABASE_URL tiene un formato de conexión inválido.") from None
    # Sin dbname, libpq puede elegir otra base según el usuario o el entorno.
    # Exigimos identificar la base donde se instalará este proyecto.
    if not params.get("dbname", "").strip():
        raise ValueError("DATABASE_URL debe indicar el nombre de la base del proyecto.")
    try:
        return psycopg.connect(database_url, connect_timeout=10,
                               application_name="grain_pipeline",
                               options="-c timezone=UTC")
    except psycopg.Error as error:
        raise RuntimeError(database_error_message(error)) from None
