"""Constructores de datos ficticios compartidos por las pruebas de metadatos."""

from grain_pipeline.sources.catalog import SERIES


def metadata_record(series: dict) -> dict:
    """Construye un registro de ejemplo con los campos esperados del catálogo."""
    if series["provider"] == "FRED":
        # Estas fechas son ejemplos ficticios de la suite, no rangos obtenidos por HTTP.
        return {"id": series["code"], "title": series["source_title"],
                "observation_start": "2010-01-01", "observation_end": "2026-09-01",
                **series["expected_metadata"]}
    return {"idSerie": series["code"], "titulo": "Tipo de cambio " + series["source_title"],
            "fechaInicio": "01/01/2010", "fechaFin": "30/10/2026",
            **series["expected_metadata"]}


def metadata_payload(series: dict, record=None) -> dict:
    """Coloca un registro ficticio en la estructura JSON de su proveedor."""
    if record is None:
        record = metadata_record(series)
    if series["provider"] == "FRED":
        return {"seriess": [record]}
    return {"bmx": {"series": [record]}}

def metadata_entries() -> list[dict]:
    """Construye las cuatro entradas ficticias que necesita el selector de muestra."""
    return [{"series": series, "metadata": metadata_record(series)} for series in SERIES]
