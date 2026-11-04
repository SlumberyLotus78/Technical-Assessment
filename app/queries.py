"""Una instantánea PostgreSQL coherente; sin APIs, capturas locales ni escrituras."""

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from grain_pipeline.persistence.schema import verify_schema
from grain_pipeline.persistence.watermarks import PRODUCT_NAME
from grain_pipeline.quality.analytics import validate_analytical_rows


def open_dashboard_connection(database_url: str) -> psycopg.Connection:
    """Fuerza lectura y tiempos de espera incluso si se utiliza una cuenta administradora."""
    try:
        params = conninfo_to_dict(database_url)
    except psycopg.Error:
        raise ValueError("La conexión de lectura tiene un formato incompatible.") from None
    if not params.get("dbname", "").strip():
        raise ValueError("La conexión de lectura debe indicar una base explícita.")
    return psycopg.connect(database_url, connect_timeout=10, application_name="grain_dashboard",
                           options="-c default_transaction_read_only=on -c timezone=UTC -c statement_timeout=10000 -c lock_timeout=5000")


def read_dashboard_snapshot(database_url: str) -> dict:
    """Watermark y filas comparten snapshot; una publicación concurrente no mezcla versiones."""
    with open_dashboard_connection(database_url) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        verify_schema(connection)
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT w.start_month, w.published_through_month, w.last_run_id, w.updated_at,
                          i.load_type AS initial_type, i.status AS initial_status, i.start_month AS initial_start,
                          i.end_month AS initial_end, r.status AS last_status, r.stage AS last_stage
                   FROM ops.watermarks w JOIN ops.runs i ON i.run_id = w.initial_run_id
                   JOIN ops.runs r ON r.run_id = w.last_run_id WHERE w.pipeline_name = %s""", (PRODUCT_NAME,))
            publication = cursor.fetchone()
            if publication is None:
                return {"publication": None, "rows": []}
            if (publication["initial_type"] != "historical" or publication["initial_status"] != "succeeded"
                    or publication["initial_start"] != publication["start_month"]
                    or publication["initial_end"] > publication["published_through_month"]
                    or publication["last_status"] != "succeeded" or publication["last_stage"] != "publication"):
                raise ValueError("El avance analítico no está respaldado por publicaciones exitosas.")
            cursor.execute(
                """SELECT g.provider, g.series_code, s.name, g.month, g.fx_provider, g.fx_series_code,
                          g.grain_price_usd_t, g.average_fix_mxn_usd, g.reference_mxn_t,
                          g.mom_change_pct, g.yoy_change_pct, f.average_fix AS fx_average,
                          f.observed_days, f.expected_days, f.calendar_reference
                   FROM mart.grain_reference_monthly g JOIN core.series s USING (provider, series_code)
                   JOIN mart.fx_monthly f ON (f.provider, f.series_code, f.month) = (g.fx_provider, g.fx_series_code, g.month)
                   WHERE g.month BETWEEN %s AND %s ORDER BY g.series_code, g.month""",
                (publication["start_month"], publication["published_through_month"]))
            rows = cursor.fetchall()
    validate_analytical_rows(rows, publication["start_month"], publication["published_through_month"])
    return {"publication": publication, "rows": rows}
