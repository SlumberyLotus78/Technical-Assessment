"""Configuración privada de APIs y PostgreSQL desde archivo y entorno.

La lectura comparte reglas de prioridad y formato. 
Cada función pública pide solo las variables de su componente, la comunicación vive en otros módulos.
"""

import os

from pathlib import Path
from dotenv import dotenv_values


def _load_required_values(env_file: Path, names: tuple[str, ...]) -> dict[str, str]:
    """Lee solo los nombres solicitados, con prioridad del entorno del proceso.
    Si falta un valor, lanza ValueError con los nombres que necesitan corregirse.
    """
    file_values = dotenv_values(env_file, encoding="utf-8-sig", interpolate=False)
    credentials = {}

    # Recorremos los nombres públicos solicitados por el componente llamador.
    for name in names:
        raw_value = os.environ.get(name, file_values.get(name))
        credentials[name] = raw_value.strip() if isinstance(raw_value, str) else ""
    missing_names = [name for name, value in credentials.items() if not value]
    if missing_names:
        raise ValueError("Faltan variables de configuración: " + ", ".join(missing_names))
    return credentials

def load_credentials(env_file: Path) -> dict[str, str]:
    """Prepara las dos credenciales de las APIs con las reglas compartidas."""
    return _load_required_values(env_file, ("FRED_API_KEY", "BANXICO_TOKEN"))


def load_database_url(env_file: Path) -> str:
    """Obtiene la conexión privada; su interpretación corresponde a persistence."""
    return _load_required_values(env_file, ("DATABASE_URL",))["DATABASE_URL"]


def load_dashboard_database_url(env_file: Path) -> str:
    file_values = dotenv_values(env_file, encoding="utf-8-sig", interpolate=False)
    name = "READONLY_DATABASE_URL" if "READONLY_DATABASE_URL" in os.environ or "READONLY_DATABASE_URL" in file_values else "DATABASE_URL"
    return _load_required_values(env_file, (name,))[name]
