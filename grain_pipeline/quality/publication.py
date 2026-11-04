"""Reglas del intervalo publicado, entradas reunidas y procedencia Silver."""

from collections import Counter
from datetime import date

from grain_pipeline.common.dates import month_end, months_between, shift_month
from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.contracts import validate_metadata_record


def plan_publication(run: dict, watermark: dict | None, *, as_of: date) -> dict:
    """Exige un histórico inicial, las ampliaciones posteriores deben ser continuas."""
    start, end = run["start_month"], run["end_month"]
    months_between(start, end)
    if type(as_of) is not date or end >= as_of.replace(day=1):
        raise ValueError("La publicación requiere meses cerrados.")
    if run["load_type"] not in {"historical", "incremental"}:
        raise ValueError("Tipo de carga incompatible con la publicación.")
    if watermark is None:
        if run["load_type"] != "historical":
            raise ValueError("El incremental requiere un histórico publicado hasta Gold.")
        return {"start_month": start, "end_month": end}
    first, last = watermark["start_month"], watermark["published_through_month"]
    months_between(first, last)
    if start < first:
        raise ValueError("Un reproceso no puede cambiar el inicio del histórico publicado.")
    # Se admite revisar un intervalo previo o ampliar desde el mes siguiente.
    if start > last and start != shift_month(last, 1):
        raise ValueError("La publicación dejaría un hueco después del watermark.")
    if last >= as_of.replace(day=1):
        raise ValueError("El watermark contiene un mes que aún no está cerrado.")
    return {"start_month": first, "end_month": max(last, end)}


def validate_capture_set(captures: list[dict], run: dict) -> dict:
    """Exige metadatos de las cuatro series y observaciones dentro del plan."""
    expected = {(series["provider"], series["code"]) for series in SERIES}
    metadata, observations = {}, []
    for capture in captures:
        key = (capture["provider"], capture["series_code"])
        if key not in expected:
            raise ValueError("La captura no corresponde al catálogo del producto.")
        if capture["kind"] == "metadata":
            if key in metadata:
                raise ValueError("Se requieren metadatos únicos por serie e intento.")
            series = next(series for series in SERIES if (series["provider"], series["code"]) == key)
            metadata[key] = validate_metadata_record(capture["payload"], series)
        elif capture["kind"] == "observations":
            if (capture["window_start"] < run["start_month"]
                    or capture["window_end"] > month_end(run["end_month"])):
                raise ValueError("Una captura queda fuera del intervalo planificado.")
            observations.append(capture)
        else:
            raise ValueError("Tipo de captura incompatible con la publicación.")
    received = {(capture["provider"], capture["series_code"]) for capture in observations}
    if set(metadata) != expected or received != expected:
        raise ValueError("La publicación requiere metadatos y observaciones de las cuatro series.")
    return {"metadata": metadata, "observations": observations}


def observation_values(records: list[dict]) -> dict:
    """Representa claves y valores sin perder duplicados mediante sobrescritura."""
    indexed = {}
    for row in records:
        key = (row["provider"], row["series_code"], row["observation_date"])
        if key in indexed:
            raise ValueError("Los fragmentos reunidos repiten una clave de observación.")
        indexed[key] = row["value"]
    return indexed


def check_combined_observations(records: list[dict], start: date, end: date) -> list[dict]:
    """Evalúa duplicados entre fragmentos y meses de granos faltantes en el conjunto."""
    keys = Counter((row["provider"], row["series_code"], row["observation_date"]) for row in records)
    duplicates = [{"provider": provider, "series_code": code, "date": day.isoformat(), "count": count}
                  for (provider, code, day), count in sorted(keys.items()) if count > 1]
    missing = [{"provider": series["provider"], "series_code": series["code"], "month": month.isoformat()}
               for series in SERIES if series["frequency"] == "monthly"
               for month in months_between(start, end) if (series["provider"], series["code"], month) not in keys]
    return [{"rule_code": "DQ-06", "status": "failed" if duplicates else "passed",
             "details": {"scope": "combined_inputs", "duplicates": duplicates}},
            {"rule_code": "DQ-08", "status": "failed" if missing else "passed",
             "details": {"scope": "combined_inputs", "missing_grain_months": missing}}]


def merge_observations(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """Combina revisiones con el histórico, valida duplicados antes de superponer."""
    values = observation_values(existing)
    values.update(observation_values(incoming))
    return [{"provider": provider, "series_code": code, "observation_date": day, "value": value}
            for (provider, code, day), value in sorted(values.items())]


def validate_silver_lineage(records: list[dict], capture_values: dict) -> None:
    """Cada valor Silver debe existir en su captura íntegra de la misma serie y fecha."""
    for row in records:
        key = (row["provider"], row["series_code"], row["observation_date"])
        original = capture_values.get(row["source_capture_id"], {})
        if key not in original or original[key] != row["value"]:
            raise ValueError("Silver no coincide con el valor y contexto de su captura Bronze.")


def validate_stored_gold(expected: dict, stored: dict) -> None:
    """Compara todas las claves y campos analíticos, no solamente sus conteos."""
    def key(row):
        return row["provider"], row["series_code"], row["month"]

    for table in ("fx_monthly", "grain_reference_monthly"):
        if sorted(expected[table], key=key) != sorted(stored[table], key=key):
            raise ValueError(f"Los valores almacenados en {table} no coinciden con el cálculo validado.")
