"""Interpretación de valores numéricos y marcadores ausentes de las fuentes."""

from decimal import Decimal
import re


# Son marcadores que trataremos explícitamente como ausentes. Otro texto desconocido se contará como inválido para que pueda investigarse.
MISSING_MARKERS = {"FRED": {"", "."}, "Banxico": {"", "N/E", "N/D"}}

def parse_source_value(value, provider: str) -> Decimal | None:
    """Devuelve un decimal exacto, None para ausentes o un error de formato."""
    if provider not in MISSING_MARKERS:
        raise ValueError("Proveedor de valores no soportado.")
    if value is None:
        return None
    # El contrato esperado de estas APIs entrega los números como texto.
    if not isinstance(value, str):
        raise ValueError("El valor de origen debe ser texto.")
    text = value.strip()
    if text in MISSING_MARKERS[provider]:
        return None

    # Banxico puede representar miles con comas. Exigimos grupos de tres dígitos '18,75' no se interpretará arbitrariamente como 18.75 o 1875.
    integer = r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)" if provider == "Banxico" else r"[0-9]+"
    if re.fullmatch(r"[+-]?" + integer + r"(?:\.[0-9]+)?", text) is None:
        raise ValueError("Formato numérico de origen inválido.")

    number = Decimal(text.replace(",", ""))
    if not number.is_finite():
        raise ValueError("El valor debe ser finito.")
    # Cero y negativos se devuelven para contarlos con una regla separada.
    return number
