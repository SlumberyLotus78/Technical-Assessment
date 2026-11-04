"""Política compartida para cálculos Gold, Silver conserva el Decimal original."""

from decimal import ROUND_HALF_EVEN

# Son dígitos significativos, no una escala fija de posiciones decimales.
DECIMAL_PRECISION = 34
DECIMAL_ROUNDING = ROUND_HALF_EVEN
