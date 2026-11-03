"""Consulta observaciones e interpreta la estructura propia de cada proveedor."""

from datetime import date

import requests

from grain_pipeline.clients.http import request_json
from grain_pipeline.sources.contracts import read_series_record


def fetch_observations(session: requests.Session, series: dict, start: date,
                       end: date, credentials: dict) -> dict:
    """Devuelve el objeto JSON completo para conservarlo antes de inspeccionarlo."""
    if start > end:
        raise ValueError("El rango de consulta de observaciones está invertido.")
    provider = series["provider"]
    code = series["code"]
    # Las fechas de consulta van en ISO en ambas APIs, aunque Banxico devuelve
    # las fechas de sus registros con otro formato: DD/MM/YYYY.
    if provider == "FRED":
        path = "series/observations"
        params = {
            "series_id": code,
            "file_type": "json",
            "observation_start": start.isoformat(),
            "observation_end": end.isoformat(),
            "sort_order": "asc",
            # lin y output_type=1 solicitan niveles, sin transformaciones ni
            # múltiples versiones históricas de una misma observación.
            "units": "lin",
            "output_type": 1,
            "limit": 100000,
            "offset": 0,
        }
    elif provider == "Banxico":
        path = f"series/{code}/datos/{start.isoformat()}/{end.isoformat()}"
        params = {"locale": "es"}
    else:
        raise ValueError("Proveedor de observaciones no soportado.")

    # El cliente conserva la responsabilidad de autenticación y transporte.
    # El llamador guardará este objeto antes de aplicar el contrato y las reglas DQ.
    return request_json(session, provider, path, params, credentials)


def read_observations(payload: dict, series: dict) -> list[dict]:
    """Comprueba la envoltura y devuelve pares date/value conservando sus textos."""
    provider = series["provider"]
    code = series["code"]
    if not isinstance(payload, dict):
        raise ValueError(f"{provider} {code}: la raíz de observaciones debe ser un objeto.")
    if any(name in payload for name in ("error", "error_code", "error_message")):
        raise ValueError(f"{provider} {code}: la fuente devolvió un error de observaciones.")

    if provider == "FRED":
        records = payload.get("observations")
        date_field, value_field = "date", "value"
        if not isinstance(records, list):
            raise ValueError(f"{provider} {code}: falta la lista de observaciones.")
        # Cada nombre de control se lee del diccionario; el desempaquetado
        # asigna los tres resultados a count, offset y limit, en ese orden.
        count, offset, limit = (payload.get(name) for name in ("count", "offset", "limit"))
        # Esta muestra debe llegar en una sola página. Si FRED declara más
        # registros que los recibidos, detenemos el diagnóstico: no truncamos.
        # type(...) is int también evita aceptar True y False como contadores.
        if (type(count) is not int or count < 0 or count != len(records)
                or type(offset) is not int or offset != 0
                or type(limit) is not int or limit <= 0 or len(records) > limit):
            raise ValueError(f"{provider} {code}: respuesta parcial o paginación incompatible.")
        output_type = payload.get("output_type")
        if payload.get("units") != "lin" or type(output_type) is not int or output_type != 1:
            raise ValueError(f"{provider} {code}: transformación de observaciones incompatible.")
    elif provider == "Banxico":
        # Reutilizamos la comprobación de estructura e identidad de una sola serie.
        record = read_series_record(payload, series)
        records = record.get("datos")
        date_field, value_field = "fecha", "dato"
    else:
        raise ValueError("Proveedor de observaciones no soportado.")

    if not isinstance(records, list):
        raise ValueError(f"{provider} {code}: falta la lista de observaciones.")
    if any(not isinstance(row, dict) or date_field not in row or value_field not in row
           for row in records):
        raise ValueError(f"{provider} {code}: campos de observación incompatibles.")

    # Construimos diccionarios nuevos con dos nombres comunes. No convertimos
    # fechas ni números aquí y tampoco modificamos la respuesta archivada.
    return [{"date": row[date_field], "value": row[value_field]} for row in records]
