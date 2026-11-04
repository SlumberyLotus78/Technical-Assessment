"""Agregado FIX mensual después de aprobar la cobertura bancaria."""

from datetime import date
from decimal import Context, Decimal, DecimalException, localcontext

from grain_pipeline.common.decimal_policy import DECIMAL_PRECISION, DECIMAL_ROUNDING
from grain_pipeline.quality.calendar import check_fix_coverage


def aggregate_monthly_fix(records: list[dict], month: date) -> dict:
    """Calcula una media reproducible, una regla pendiente también bloquea Gold."""
    check = check_fix_coverage(records, month)
    if check["status"] != "passed":
        raise ValueError(f"DQ-09 {check['status']}: FIX no certificado para {month:%Y-%m}.")
    try:
        # Context crea la política completa, independiente del contexto del llamador.
        # localcontext la activa aquí y restaura el contexto anterior al salir.
        with localcontext(Context(prec=DECIMAL_PRECISION, rounding=DECIMAL_ROUNDING)):
            ordered = sorted(records, key=lambda row: row["observation_date"])
            average = sum((row["value"] for row in ordered), Decimal(0)) / Decimal(len(ordered))
    except DecimalException:
        raise ValueError("La media FIX excede el rango decimal del cálculo.") from None
    if not average.is_finite() or average <= 0:
        raise ValueError("La media FIX debe conservar un valor finito y positivo.")
    return {"provider": "Banxico", "series_code": "SF43718", "month": month,
            "average_fix": average, "observed_days": len(records),
            "expected_days": check["details"]["expected_days"],
            "calendar_reference": check["details"]["calendar_reference"]}
