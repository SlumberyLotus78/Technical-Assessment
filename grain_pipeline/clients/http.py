"""Peticiones GET autenticadas que esperan un objeto JSON como respuesta."""

import requests

BASE_URLS = {
    "FRED": "https://api.stlouisfed.org/fred/",
    "Banxico": "https://www.banxico.org.mx/SieAPIRest/service/v1/",
}

# Primer valor: espera para conectar. Segundo: espera de lectura entre datos.
TIMEOUT = (10, 30)


def request_json(session: requests.Session, provider: str, path: str,
                 params: dict, credentials: dict) -> dict:
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

    try:
        # session permite reutilizar conexiones. allow_redirects=False hace explícito que una redirección deberá revisarse como respuesta HTTP.
        
        response = session.get(url, params=private_params, headers=headers,
                               timeout=TIMEOUT, allow_redirects=False)
    except requests.RequestException as error:
        # Algunas excepciones incluyen la URL completa, que en FRED lleva la clave.
        # Informamos solo el proveedor y el tipo de excepción. from None suprime
        # la presentación de la excepción original en el traceback habitual.
        raise RuntimeError(f"{provider}: fallo de conexión ({type(error).__name__}).") from None

    try:
        # Los endpoints JSON de metadatos y observaciones deben responder HTTP 200.
        if response.status_code != 200:
            raise RuntimeError(f"{provider}: respuesta HTTP {response.status_code}.")

        # Separar por ; permite aceptar application/json; charset=utf-8.
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold()
        if content_type != "application/json":
            raise RuntimeError(f"{provider}: se esperaba una respuesta JSON.")

        try:
            # json convierte el cuerpo recibido en objetos Python.
            payload = response.json()
        except ValueError:
            raise RuntimeError(f"{provider}: el contenido JSON es inválido.") from None

        # El contrato de esta función exige un objeto JSON, representado por dict.
        if not isinstance(payload, dict):
            raise RuntimeError(f"{provider}: la raíz JSON debe ser un objeto.")
        return payload
    finally:
        # Liberamos los recursos de la respuesta en ambas situaciones.
        response.close()
