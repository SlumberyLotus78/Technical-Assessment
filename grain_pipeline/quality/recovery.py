"""Decisión de recuperación a partir del estado durable, sin modificar datos."""

from collections import Counter

from grain_pipeline.sources.catalog import SERIES
from grain_pipeline.sources.windows import yearly_query_windows


def recovery_decision(attempt: dict, captures: list[dict], *, newer_publication: bool) -> dict:
    """Solo permite reutilizar una extracción completa que no haya quedado antigua."""
    if attempt["status"] in {"succeeded", "skipped"}:
        return {"action": "already_completed", "reason": "terminal_success"}
    if attempt["status"] not in {"running", "failed"}:
        raise ValueError("Estado incompatible con la recuperación.")
    if newer_publication:
        return {"action": "retry_required", "reason": "newer_publication"}
    if attempt["start_month"] is None:
        return {"action": "retry_required", "reason": "unplanned_window"}
    windows = yearly_query_windows(attempt["start_month"], attempt["end_month"])
    expected = Counter()
    for series in SERIES:
        identity = (series["provider"], series["code"])
        expected[(*identity, "metadata", None, None)] += 1
        for first, last in windows:
            expected[(*identity, "observations", first, last)] += 1
    actual = Counter((row["provider"], row["series_code"], row["kind"], row["window_start"], row["window_end"])
                     for row in captures)
    if actual != expected:
        return {"action": "retry_required", "reason": "incomplete_capture_set"}
    return {"action": "reuse_captures", "reason": "complete_registered_extraction"}
