"""Peticiones GET autenticadas que esperan un objeto JSON como respuesta."""

import requests
import time
from grain_pipeline.clients.retry import MAX_ATTEMPTS, RETRYABLE_STATUSES, retry_delay

BASE_URLS = {
    "FRED": "https://api.stlouisfed.org/fred/",
    "Banxico": "https://www.banxico.org.mx/SieAPIRest/service/v1/",
}

# Primer valor: espera para conectar. Segundo: espera de lectura entre datos.
TIMEOUT = (10, 30)


def request_json(session: requests.Session, provider: str, path: str,
                 params: dict, credentials: dict, *, max_attempts: int = MAX_ATTEMPTS) -> dict:
    """Devuelve JSON con reintentos acotados solo para fallos transitorios GET."""
    if type(max_attempts) is not int or not 1 <= max_attempts <= MAX_ATTEMPTS:
        raise ValueError("La petición requiere entre uno y tres intentos.")
    if provider not in BASE_URLS or not path or path.startswith("/"):
        raise ValueError("Proveedor o ruta no permitidos.")
    if any(character in path for character in (":", "?", "#", "\\")):
        raise ValueError("La ruta debe ser relativa y sus parámetros deben ir separados.")
    if any(part in {".", "..", ""} for part in path.split("/")):
        raise ValueError("La ruta contiene segmentos no permitidos.")

    private_names = {"api_key", "token", "bmx-token", "bmx_token",
                     "fred_api_key", "banxico_token"}
    if any(name.casefold() in private_names for name in params):
        raise ValueError("Las credenciales deben entregarse separadas de los parámetros públicos.")

    url = BASE_URLS[provider] + path
    private_params = dict(params)
    headers = {"Accept": "application/json"}
    if provider == "FRED":
        private_params["api_key"] = credentials["FRED_API_KEY"]
    else:
        headers["Bmx-Token"] = credentials["BANXICO_TOKEN"]

    for attempt in range(1, max_attempts + 1):
        try:
            response = session.get(url, params=private_params, headers=headers,
                                   timeout=TIMEOUT, allow_redirects=False)
        except requests.RequestException as error:
            transient = isinstance(error, (requests.Timeout, requests.ConnectionError))
            transient = transient and not isinstance(error, requests.exceptions.SSLError)
            if transient and attempt < max_attempts:
                time.sleep(retry_delay(attempt))
                continue
            # Nunca se imprime el texto externo, que puede contener la URL FRED.
            raise RuntimeError(f"{provider}: fallo de conexión ({type(error).__name__}).") from None

        wait = None
        try:
            if response.status_code != 200:
                if response.status_code in RETRYABLE_STATUSES and attempt < max_attempts:
                    wait = retry_delay(attempt, response.headers.get("Retry-After"))
                if wait is None:
                    raise RuntimeError(f"{provider}: respuesta HTTP {response.status_code}.")
            else:
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold()
                if content_type != "application/json":
                    raise RuntimeError(f"{provider}: se esperaba una respuesta JSON.")
                try:
                    payload = response.json()
                except ValueError:
                    raise RuntimeError(f"{provider}: el contenido JSON es inválido.") from None
                if not isinstance(payload, dict):
                    raise RuntimeError(f"{provider}: la raíz JSON debe ser un objeto.")
                return payload
        finally:
            response.close()  # Se libera también ANTES de esperar otro intento.
        time.sleep(wait)
