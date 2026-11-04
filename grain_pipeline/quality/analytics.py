"""Contrato de lectura analítica: producto publicado completo y fórmulas conciliadas."""

from decimal import Context, Decimal, DecimalException, localcontext

from grain_pipeline.common.dates import months_between
from grain_pipeline.common.decimal_policy import DECIMAL_PRECISION, DECIMAL_ROUNDING
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.transformations.gold import add_reference_changes


def validate_analytical_rows(rows: list[dict], start, end) -> None:
    """El dashboard rechaza un Gold incompleto o incongruente en vez de ocultar huecos."""
    grains = {series["code"] for series in SERIES if series["frequency"] == "monthly"}
    expected = {(code, month) for code in grains for month in months_between(start, end)}
    keys = [(row["series_code"], row["month"]) for row in rows]
    if len(keys) != len(expected) or set(keys) != expected:
        raise ValueError("Gold no contiene los tres granos en cada mes del intervalo publicado.")
    fixes = {}
    with localcontext(Context(prec=DECIMAL_PRECISION, rounding=DECIMAL_ROUNDING)):
        for row in rows:
            values = [row[field] for field in ("grain_price_usd_t", "average_fix_mxn_usd", "reference_mxn_t", "fx_average")]
            if any(not isinstance(value, Decimal) or not value.is_finite() or value <= 0 for value in values):
                raise ValueError("Gold contiene valores incompatibles con el análisis.")
            try:
                expected_reference = row["grain_price_usd_t"] * row["average_fix_mxn_usd"]
            except DecimalException:
                raise ValueError("La referencia excede el rango decimal del análisis.") from None
            if (row["provider"] != "FRED" or row["fx_provider"] != "Banxico" or row["fx_series_code"] != "SF43718"
                    or row["average_fix_mxn_usd"] != row["fx_average"]
                    or expected_reference != row["reference_mxn_t"]):
                raise ValueError("La referencia Gold no concuerda con su precio y FIX publicados.")
            if (type(row["observed_days"]) is not int or type(row["expected_days"]) is not int
                    or row["observed_days"] <= 0 or row["observed_days"] != row["expected_days"]
                    or not isinstance(row["calendar_reference"], str) or not row["calendar_reference"].strip()):
                raise ValueError("El FIX mensual no tiene una cobertura certificada compatible.")
            signature = (row["fx_average"], row["observed_days"], row["expected_days"], row["calendar_reference"])
            if fixes.setdefault(row["month"], signature) != signature:
                raise ValueError("Los granos no comparten el mismo FIX mensual.")
    calculated = add_reference_changes(rows)
    by_key = {(row["series_code"], row["month"]): row for row in calculated}
    for row in rows:
        expected_row = by_key[(row["series_code"], row["month"])]
        if any(row[field] != expected_row[field] for field in ("mom_change_pct", "yoy_change_pct")):
            raise ValueError("Las variaciones Gold no coinciden con sus comparadores exactos.")
