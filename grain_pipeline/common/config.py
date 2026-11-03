"""Lectura de credenciales desde un archivo explícito y el entorno del proceso."""

import os
from pathlib import Path

from dotenv import dotenv_values


def load_credentials(env_file: Path) -> dict[str, str]:
    """Devuelve las claves requeridas; las variables del entorno tienen prioridad."""
    file_values = dotenv_values(env_file, encoding="utf-8-sig", interpolate=False)
    credentials = {}

    for name in ("FRED_API_KEY", "BANXICO_TOKEN"):
        # Una variable del entorno vacía también prevalece sobre el archivo.
        raw_value = os.environ.get(name, file_values.get(name))
        credentials[name] = raw_value.strip() if isinstance(raw_value, str) else ""

    missing_names = [name for name, value in credentials.items() if not value]
    if missing_names:
        raise ValueError("Faltan credenciales: " + ", ".join(missing_names))

    return credentials
