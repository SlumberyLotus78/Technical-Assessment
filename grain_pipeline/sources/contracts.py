"""Reglas de entrada para los metadatos de las fuentes.

Estas funciones reciben diccionarios y comprueban su contenido. Sus entradas
pueden proceder del cliente HTTP o de un escenario de prueba preparado.
"""

from datetime import date
from grain_pipeline.common.dates import parse_date

def normalize_text(value) -> str:
    """Prepara texto para comparar espacios y mayúsculas sin alterar el original."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).casefold()


def read_series_record(payload: dict, series: dict) -> dict:
    """Lee una serie de metadatos o de la envoltura de observaciones Banxico."""
    provider = series["provider"]
    code = series["code"]
    if not isinstance(payload, dict):
        raise ValueError(f"{provider} {code}: la raíz de la respuesta debe ser un objeto.")
    # Un JSON con un error declarado tampoco satisface el contrato.
    if any(name in payload for name in ("error", "error_code", "error_message")):
        raise ValueError(f"{provider} {code}: la fuente devolvió un error.")

    # Esta interpretación de campos pertenece al contrato de la fuente.
    # FRED usa seriess y Banxico usa bmx.series.
    if provider == "FRED":
        records = payload.get("seriess")
        identifier_field = "id"
    elif provider == "Banxico":
        bmx = payload.get("bmx")
        records = bmx.get("series") if isinstance(bmx, dict) and "error" not in bmx else None
        identifier_field = "idSerie"
    else:
        raise ValueError("Proveedor de metadatos no soportado.")

    # Cada petición del diagnóstico consulta exactamente una serie. Banxico utiliza esta misma envoltura al consultar metadatos y observaciones.
    if not isinstance(records, list) or len(records) != 1:
        raise ValueError(f"{provider} {code}: estructura de serie inesperada.")
    record = records[0]
    if not isinstance(record, dict) or "error" in record:
        raise ValueError(f"{provider} {code}: registro de serie incompatible.")
    if record.get(identifier_field) != code:
        raise ValueError(f"{provider} {code}: identificador recibido incompatible.")
    return record


def read_metadata_range(record: dict, series: dict) -> tuple[date, date]:
    """Lee el inicio y fin declarados por el proveedor como objetos date."""
    provider = series["provider"]
    code = series["code"]
    if provider == "FRED":
        start_field, end_field = "observation_start", "observation_end"
        iso = True
    elif provider == "Banxico":
        start_field, end_field = "fechaInicio", "fechaFin"
        iso = False
    else:
        raise ValueError("Proveedor de metadatos no soportado.")

    try:
        # El proveedor determina el formato; el helper común interpreta la fecha.
        start = parse_date(record.get(start_field), iso=iso)
        end = parse_date(record.get(end_field), iso=iso)
    except ValueError:
        raise ValueError(f"{provider} {code}: formato o fecha de disponibilidad inválidos.") from None

    if start > end:
        raise ValueError(f"{provider} {code}: rango de disponibilidad invertido.")
    # En nuestras series mensuales, el primer día identifica el periodo del mes.
    if provider == "FRED" and (start.day != 1 or end.day != 1):
        raise ValueError(f"{provider} {code}: fechas de periodo mensual incompatibles.")
    return start, end


def validate_metadata(payload: dict, series: dict) -> dict:
    """Comprueba identidad, título y campos requeridos; devuelve el registro original."""
    record = read_series_record(payload, series)
    provider = series["provider"]
    code = series["code"]

    # items entrega cada nombre de campo con su valor esperado.
    for field, expected_value in series["expected_metadata"].items():
        if normalize_text(record.get(field)) != normalize_text(expected_value):
            # El mensaje identifica el campo incompatible sin volcar la respuesta.
            raise ValueError(f"{provider} {code}: metadato {field} incompatible.")

    title_field = "title" if provider == "FRED" else "titulo"
    received_title = normalize_text(record.get(title_field))
    expected_title = normalize_text(series["source_title"])
    if provider == "FRED":
        title_matches = received_title == expected_title
    else:
        # El título jerárquico de Banxico puede incluir contexto adicional.
        # Comprobamos que contenga el componente de determinación FIX esperado.
        title_matches = expected_title in received_title
    if not title_matches:
        raise ValueError(f"{provider} {code}: metadato {title_field} incompatible.")

    # También exigimos un rango de fechas interpretable y ordenado.
    read_metadata_range(record, series)

    return record
