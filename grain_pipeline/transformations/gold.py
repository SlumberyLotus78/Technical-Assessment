"""Referencias mensuales MXN/t y variaciones por fechas exactas, sin escritura SQL."""

from datetime import date
from decimal import Context, Decimal, DecimalException, localcontext

from grain_pipeline.common.dates import months_between, shift_month
from grain_pipeline.common.decimal_policy import DECIMAL_PRECISION, DECIMAL_ROUNDING
from grain_pipeline.quality.gold import validate_gold_inputs
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.transformations.monthly_fx import aggregate_monthly_fix


def add_reference_changes(references: list[dict]) -> list[dict]:
    """Añade MoM y YoY a referencias calculadas."""
    if not references:
        raise ValueError("Las variaciones requieren referencias mensuales.")
    indexed = {}
    for row in references:
        month, value = row["month"], row["reference_mxn_t"]
        if (type(month) is not date or month.day != 1 or not isinstance(value, Decimal)
                or not value.is_finite() or value <= 0):
            raise ValueError("Referencia incompatible con las variaciones.")
        key = (row["provider"], row["series_code"], month)
        if key in indexed:
            raise ValueError("Las referencias repiten una clave mensual.")
        indexed[key] = row
    start, end = min(key[2] for key in indexed), max(key[2] for key in indexed)
    series_keys = {(key[0], key[1]) for key in indexed}
    if any((provider, code, month) not in indexed for provider, code in series_keys
           for month in months_between(start, end)):
        raise ValueError("Las referencias tienen meses ausentes dentro del intervalo.")

    result = []
    try:
        with localcontext(Context(prec=DECIMAL_PRECISION, rounding=DECIMAL_ROUNDING)):
            for (provider, code, month), row in sorted(indexed.items()):
                changes = {}
                for field, offset in (("mom_change_pct", -1), ("yoy_change_pct", -12)):
                    months_since_year_one = (month.year - 1) * 12 + month.month - 1
                    target = shift_month(month, offset) if months_since_year_one >= -offset else None
                    previous = indexed.get((provider, code, target))
                    changes[field] = (None if previous is None else
                                      (row["reference_mxn_t"] / previous["reference_mxn_t"] - 1) * 100)
                result.append({**row, **changes})
    except DecimalException:
        raise ValueError("Las variaciones exceden el rango decimal del cálculo.") from None
    return result


def build_monthly_gold(records: list[dict], start: date, end: date, *, as_of: date) -> dict:
    """Construye un intervalo completo; histórico e incremental compartirán esta función."""
    indexed = validate_gold_inputs(records, start, end, as_of)
    fix_by_month = {month: [] for month in months_between(start, end)}
    for (provider, code, day), row in indexed.items():
        if provider == "Banxico" and code == "SF43718":
            fix_by_month[day.replace(day=1)].append(row)
    monthly_fx, references = [], []
    for month, daily_fix in fix_by_month.items():
        fx = aggregate_monthly_fix(daily_fix, month)
        monthly_fx.append(fx)
        try:
            with localcontext(Context(prec=DECIMAL_PRECISION, rounding=DECIMAL_ROUNDING)):
                for series in SERIES:
                    if series["frequency"] != "monthly":
                        continue
                    grain = indexed[(series["provider"], series["code"], month)]
                    # El producto usa la media que se devolverá para mart.fx_monthly.
                    value = grain["value"] * fx["average_fix"]
                    references.append({"provider": grain["provider"], "series_code": grain["series_code"],
                                       "month": month, "fx_provider": fx["provider"],
                                       "fx_series_code": fx["series_code"], "grain_price_usd_t": grain["value"],
                                       "average_fix_mxn_usd": fx["average_fix"], "reference_mxn_t": value})
        except DecimalException:
            raise ValueError("La referencia MXN/t excede el rango decimal del cálculo.") from None
    return {"fx_monthly": monthly_fx, "grain_reference_monthly": add_reference_changes(references)}
