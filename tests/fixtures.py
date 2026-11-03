"""Constructores de datos ficticios compartidos por las pruebas de metadatos."""


def metadata_record(series: dict) -> dict:
    """Construye un registro de ejemplo con los campos esperados del catálogo."""
    # ** copia las entradas al diccionario nuevo. Cambiar el registro de una
    # prueba no modifica los valores compartidos de expected_metadata.
    if series["provider"] == "FRED":
        return {"id": series["code"], "title": series["source_title"],
                **series["expected_metadata"]}
    return {"idSerie": series["code"], "titulo": "Tipo de cambio " + series["source_title"],
            **series["expected_metadata"]}


def metadata_payload(series: dict, record=None) -> dict:
    """Coloca un registro ficticio en la estructura JSON de su proveedor."""
    if record is None:
        record = metadata_record(series)
    if series["provider"] == "FRED":
        return {"seriess": [record]}
    return {"bmx": {"series": [record]}}
