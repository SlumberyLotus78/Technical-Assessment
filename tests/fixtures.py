"""Constructores de respuestas ficticias: no consultan las APIs ni leen .env."""

from datetime import date
from decimal import Decimal
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


def observation_rows(series: dict) -> list[dict]:
    """Ejemplos mensuales o diarios para la muestra ficticia de septiembre."""
    if series["provider"] == "FRED":
        return [{"date": "2026-07-01", "value": "100.1234567890123456789"},
                {"date": "2026-08-01", "value": "102.50"},
                {"date": "2026-09-01", "value": "105.75"}]
    return [{"fecha": "01/09/2026", "dato": "18.1234"},
            {"fecha": "02/09/2026", "dato": "18.5678"}]


def observations_payload(series: dict, rows=None) -> dict:
    """Coloca observaciones ficticias en la envoltura nativa del proveedor."""
    if rows is None:
        rows = observation_rows(series)
    if series["provider"] == "FRED":
        return {"count": len(rows), "offset": 0, "limit": 100000,
                "units": "lin", "output_type": 1, "observations": rows}
    return {"bmx": {"series": [{"idSerie": series["code"],
                                "titulo": series["source_title"], "datos": rows}]}}


FIX_SAMPLE_MONTH = date(2026, 9, 1)


def september_fix() -> list[dict]:
    """Datos ficticios: fechas bancarias de septiembre y un FIX constante."""
    return [{"provider": "Banxico", "series_code": "SF43718", "observation_date": date(2026, 9, day),
             "value": Decimal("20")} for day in
            (1, 2, 3, 4, 7, 8, 9, 10, 11, 14, 15, 17, 18, 21, 22, 23, 24, 25, 28, 29, 30)]
