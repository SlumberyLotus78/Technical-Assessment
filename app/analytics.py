"""Indicadores de análisis con Decimal; independientes de Streamlit y de PostgreSQL."""

from datetime import date
from decimal import Context, Decimal, DecimalException, localcontext

from grain_pipeline.common.dates import months_between, shift_month
from grain_pipeline.common.decimal_policy import DECIMAL_PRECISION, DECIMAL_ROUNDING


def build_analysis(rows: list[dict], start: date, end: date) -> dict:
    """Índices sobre la selección y atribución simétrica del cambio mensual de P × F."""
    months_between(start, end)
    selected = [dict(row) for row in rows if start <= row["month"] <= end]
    if not selected:
        raise ValueError("El periodo seleccionado no contiene referencias publicadas.")
    indexed = {(row["series_code"], row["month"]): row for row in rows}
    summaries, result = [], []
    try:
        with localcontext(Context(prec=DECIMAL_PRECISION, rounding=DECIMAL_ROUNDING)):
            for code in sorted({row["series_code"] for row in selected}):
                series = sorted((row for row in selected if row["series_code"] == code), key=lambda row: row["month"])
                first, last = series[0], series[-1]
                declines = cancelled = compared = 0
                for row in series:
                    # Se usa el mes calendario anterior, aunque quede fuera del
                    # filtro visible; nunca se sustituye por otra fecha disponible.
                    previous_month = shift_month(row["month"], -1) if row["month"] > date(1, 1, 1) else None
                    previous = indexed.get((code, previous_month))
                    detail = dict(row, usd_index=100 * row["grain_price_usd_t"] / first["grain_price_usd_t"],
                                  mxn_index=100 * row["reference_mxn_t"] / first["reference_mxn_t"],
                                  grain_contribution_mxn=None, fx_contribution_mxn=None,
                                  grain_contribution_pp=None, fx_contribution_pp=None)
                    if previous is not None:
                        price, old_price = row["grain_price_usd_t"], previous["grain_price_usd_t"]
                        fix, old_fix = row["average_fix_mxn_usd"], previous["average_fix_mxn_usd"]
                        grain = (price - old_price) * (fix + old_fix) / 2
                        currency = (fix - old_fix) * (price + old_price) / 2
                        detail.update(grain_contribution_mxn=grain, fx_contribution_mxn=currency,
                                      grain_contribution_pp=100 * grain / previous["reference_mxn_t"],
                                      fx_contribution_pp=100 * currency / previous["reference_mxn_t"])
                        compared += 1
                        if price < old_price:
                            declines += 1
                            cancelled += row["reference_mxn_t"] >= previous["reference_mxn_t"]
                    result.append(detail)
                summaries.append({"name": first["name"], "series_code": code,
                                  "cumulative_pct": 100 * (last["reference_mxn_t"] / first["reference_mxn_t"] - 1),
                                  "international_declines": declines, "cancelled_declines": cancelled,
                                  "cancelled_pct": 100 * Decimal(cancelled) / declines if declines else None,
                                  "comparable_months": compared, "excluded_months": len(series) - compared})
    except (DecimalException, ZeroDivisionError):
        raise ValueError("Los indicadores exceden el rango decimal del análisis.") from None
    return {"rows": result, "summary": summaries, "start_month": start, "end_month": end}


def describe_findings(analysis: dict) -> list[str]:
    """Textos basados en la selección, sin inferencias de causalidad económica."""
    summaries = analysis["summary"]
    highest = max(summaries, key=lambda row: row["cumulative_pct"])
    lowest = min(summaries, key=lambda row: row["cumulative_pct"])
    return [f"Mayor variación acumulada en MXN/t: {highest['name']} ({highest['cumulative_pct']:+.2f}%).",
            f"Menor variación acumulada en MXN/t: {lowest['name']} ({lowest['cumulative_pct']:+.2f}%).",
            "La atribución reparte simétricamente el cambio mensual entre precio internacional y FIX; describe una identidad matemática."]
