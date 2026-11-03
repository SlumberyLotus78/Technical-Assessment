"""Perfil de observaciones: fechas, valores, duplicados y periodos mensuales."""

from datetime import date

from grain_pipeline.common.dates import month_end, parse_date, shift_month
from grain_pipeline.quality.values import parse_source_value


def profile_observations(records: list[dict], series: dict, start: date, end: date) -> dict:
    """Resume incidencias sin corregir, descartar ni sobrescribir registros."""
    if start > end:
        raise ValueError("El rango del perfil está invertido.")
    provider = series["provider"]
    frequency = series["frequency"]
    if provider not in {"FRED", "Banxico"} or frequency not in {"monthly", "daily"}:
        raise ValueError("Proveedor o frecuencia de perfil no soportados.")
    if frequency == "monthly" and (start.day != 1 or end != month_end(end)):
        raise ValueError("El perfil mensual requiere meses calendario completos.")

    counts = {"missing_values": 0, "invalid_values": 0, "non_positive_values": 0,
              "invalid_dates": 0, "outside_window": 0, "non_month_start_dates": 0,
              "duplicate_dates": 0}
    dates = []
    numbers = []
    seen_dates = set()
    usable_months = set()
    for row in records:
        observed_date = None
        try:
            observed_date = parse_date(row["date"], iso=provider == "FRED")
        except ValueError:
            counts["invalid_dates"] += 1
        else:
            dates.append(observed_date)
            if not start <= observed_date <= end:
                counts["outside_window"] += 1
            if frequency == "monthly" and observed_date.day != 1:
                counts["non_month_start_dates"] += 1
            # Un duplicado es cada aparición adicional de la misma fecha.
            if observed_date in seen_dates:
                counts["duplicate_dates"] += 1
            seen_dates.add(observed_date)

        number = None
        try:
            number = parse_source_value(row["value"], provider)
        except ValueError:
            counts["invalid_values"] += 1
        else:
            if number is None:
                counts["missing_values"] += 1
            else:
                numbers.append(number)
                if number <= 0:
                    counts["non_positive_values"] += 1

        # Un mes con fecha correcta y un valor positivo aporta cobertura mensual.
        # Los duplicados siguen registrados como incidencia por separado.
        if (frequency == "monthly" and observed_date is not None
                and start <= observed_date <= end and observed_date.day == 1
                and number is not None and number > 0):
            usable_months.add(observed_date)

    expected_months = None
    missing_months = []
    if frequency == "monthly":
        # La resta de posiciones de mes incluye cambios de año sin restar días.
        expected_months = (end.year - start.year) * 12 + end.month - start.month + 1
        expected_dates = {shift_month(start, index) for index in range(expected_months)}
        missing_months = [day.isoformat() for day in sorted(expected_dates - usable_months)]

    # Cada contador es independiente: una fila puede tener más de un problema.
    # Los extremos numéricos se escriben como texto para conservar su precisión
    # al guardar el perfil en JSON, que no tiene un tipo Decimal estándar.
    return {
        "provider": provider,
        "series_code": series["code"],
        "unit": series["unit"],
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "rows": len(records),
        "numeric_values": len(numbers),
        **counts,
        "observed_start": min(dates).isoformat() if dates else None,
        "observed_end": max(dates).isoformat() if dates else None,
        "value_min": str(min(numbers)) if numbers else None,
        "value_max": str(max(numbers)) if numbers else None,
        "expected_months": expected_months,
        "missing_months": missing_months,
        # El calendario hábil bancario será una regla posterior. No sustituimos esa comprobación por exigir 30/31 registros ni por contar lunes a viernes.
        "coverage_status": "monthly_values_checked" if frequency == "monthly"
                           else "pending_banking_calendar",
        "has_issues": not records or any(counts.values()) or bool(missing_months),
    }
