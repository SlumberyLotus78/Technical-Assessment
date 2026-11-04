"""Política acotada de reintentos GET, no incluye autenticación ni reglas de datos."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re


MAX_ATTEMPTS = 3
MAX_WAIT_SECONDS = 30
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def retry_delay(attempt: int, retry_after=None, *, now: datetime | None = None) -> float | None:
    """Devuelve segundos de espera o None si el servidor exige una espera mayor."""
    delay = min(2 ** (attempt - 1), MAX_WAIT_SECONDS)
    if isinstance(retry_after, str) and retry_after.strip():
        value = retry_after.strip()
        if re.fullmatch(r"[0-9]+", value):
            digits = value.lstrip("0") or "0"
            if len(digits) > 6:
                return None
            delay = int(digits)
        else:
            try:
                requested = parsedate_to_datetime(value)
                if requested.tzinfo is not None:
                    current = datetime.now(timezone.utc) if now is None else now
                    delay = max(0, (requested - current).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass  # Un encabezado incompatible utiliza la espera exponencial.
    # No acortamos Retry-After: si excede el límite se detiene el intento.
    return None if delay > MAX_WAIT_SECONDS else delay
