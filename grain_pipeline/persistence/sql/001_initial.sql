-- Versión inicial: ocho tablas de negocio y una tabla técnica de versiones.
-- initialize.py ejecuta todo dentro de una transacción y rechaza esquemas
-- ocupados sin una versión reconocida. Este archivo se conserva una vez aplicado.

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS ops;

-- Registro técnico: identifica exactamente qué SQL instaló las tablas.
CREATE TABLE ops.schema_migrations (
    version TEXT PRIMARY KEY,
    checksum TEXT NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Catálogo: unidad y frecuencia se interpretan junto con proveedor y serie.
CREATE TABLE core.series (
    provider TEXT NOT NULL CHECK (provider IN ('FRED', 'Banxico')),
    series_code TEXT NOT NULL CHECK (btrim(series_code) <> ''),
    name TEXT NOT NULL CHECK (btrim(name) <> ''),
    unit TEXT NOT NULL CHECK (btrim(unit) <> ''),
    frequency TEXT NOT NULL CHECK (frequency IN ('monthly', 'daily')),
    source_title TEXT NOT NULL CHECK (btrim(source_title) <> ''),
    expected_metadata JSONB NOT NULL CHECK (jsonb_typeof(expected_metadata) = 'object'),
    PRIMARY KEY (provider, series_code)
);

-- Un intento se registra antes de extraer. El éxito de la futura carga se
-- confirmará junto con Silver, Gold y watermark, mediante su publicador.
CREATE TABLE ops.runs (
    run_id UUID PRIMARY KEY,
    load_type TEXT NOT NULL CHECK (load_type IN ('historical', 'incremental')),
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'skipped')),
    stage TEXT NOT NULL CHECK (stage IN ('planning', 'extraction', 'quality', 'silver', 'gold', 'publication')),
    start_month DATE,
    end_month DATE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (isfinite(started_at)),
    finished_at TIMESTAMPTZ,
    error_summary TEXT,
    CONSTRAINT runs_month_interval CHECK (
        (start_month IS NULL AND end_month IS NULL)
        OR (start_month IS NOT NULL AND end_month IS NOT NULL
            AND isfinite(start_month) AND isfinite(end_month)
            AND EXTRACT(DAY FROM start_month) = 1 AND EXTRACT(DAY FROM end_month) = 1
            AND start_month <= end_month)
    ),
    CONSTRAINT runs_finish_time CHECK (
        finished_at IS NULL OR (isfinite(finished_at) AND finished_at >= started_at)
    ),
    CONSTRAINT runs_status_fields CHECK (
        (status = 'running' AND finished_at IS NULL AND error_summary IS NULL)
        OR (status = 'failed' AND finished_at IS NOT NULL
            AND error_summary IS NOT NULL AND btrim(error_summary) <> '')
        OR (status = 'succeeded' AND finished_at IS NOT NULL AND error_summary IS NULL
            AND start_month IS NOT NULL AND stage = 'publication')
        OR (status = 'skipped' AND finished_at IS NOT NULL AND error_summary IS NULL
            AND load_type = 'incremental' AND stage = 'planning')
    )
);

-- Bronze permanece en archivos; esta tabla registra su ubicación e integridad.
CREATE TABLE ops.raw_captures (
    capture_id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES ops.runs (run_id),
    provider TEXT NOT NULL,
    series_code TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('metadata', 'observations')),
    storage_path TEXT NOT NULL UNIQUE CHECK (btrim(storage_path) <> ''),
    content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    captured_at TIMESTAMPTZ NOT NULL CHECK (isfinite(captured_at)),
    window_start DATE,
    window_end DATE,
    FOREIGN KEY (provider, series_code) REFERENCES core.series (provider, series_code),
    CONSTRAINT raw_captures_window CHECK (
        (kind = 'metadata' AND window_start IS NULL AND window_end IS NULL)
        OR (kind = 'observations' AND window_start IS NOT NULL AND window_end IS NOT NULL
            AND isfinite(window_start) AND isfinite(window_end) AND window_start <= window_end)
    )
);
CREATE INDEX raw_captures_run_series_idx ON ops.raw_captures (run_id, provider, series_code);

-- Silver: una sola fila vigente por clave natural. Las comprobaciones de
-- frecuencia, serie de captura y tipo de captura se aplicarán en la carga.
CREATE TABLE core.observations (
    provider TEXT NOT NULL,
    series_code TEXT NOT NULL,
    observation_date DATE NOT NULL CHECK (isfinite(observation_date)),
    value NUMERIC NOT NULL,
    source_capture_id UUID NOT NULL REFERENCES ops.raw_captures (capture_id),
    created_run_id UUID NOT NULL REFERENCES ops.runs (run_id),
    updated_run_id UUID NOT NULL REFERENCES ops.runs (run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (isfinite(created_at)),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (isfinite(updated_at)),
    PRIMARY KEY (provider, series_code, observation_date),
    FOREIGN KEY (provider, series_code) REFERENCES core.series (provider, series_code),
    -- PostgreSQL admite NaN e infinitos en NUMERIC. > 0 por sí solo no basta.
    CONSTRAINT observations_positive_finite CHECK (
        value > 0 AND value NOT IN ('NaN'::NUMERIC, 'Infinity'::NUMERIC, '-Infinity'::NUMERIC)
    ),
    CONSTRAINT observations_update_time CHECK (updated_at >= created_at)
);
CREATE INDEX observations_capture_idx ON core.observations (source_capture_id);

-- Métricas DQ variables se guardan en details; estado y alcance son explícitos.
CREATE TABLE ops.dq_results (
    dq_result_id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES ops.runs (run_id),
    rule_code TEXT NOT NULL CHECK (rule_code ~ '^(SRC|DQ|LIN|PUB|CTL)-[0-9]{2}$'),
    provider TEXT,
    series_code TEXT,
    period_start DATE NOT NULL CHECK (isfinite(period_start)),
    period_end DATE NOT NULL CHECK (isfinite(period_end)),
    status TEXT NOT NULL CHECK (status IN ('passed', 'failed', 'pending')),
    details JSONB NOT NULL CHECK (jsonb_typeof(details) = 'object'),
    checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (isfinite(checked_at)),
    FOREIGN KEY (provider, series_code) REFERENCES core.series (provider, series_code),
    CONSTRAINT dq_results_scope CHECK ((provider IS NULL) = (series_code IS NULL)),
    CONSTRAINT dq_results_period CHECK (period_start <= period_end)
);
CREATE INDEX dq_results_run_rule_idx ON ops.dq_results (run_id, rule_code);

-- Gold FIX: la igualdad de conteos refuerza el agregado; el calendario se
-- certificará comparando los conjuntos de fechas antes de insertar esta fila.
CREATE TABLE mart.fx_monthly (
    provider TEXT NOT NULL,
    series_code TEXT NOT NULL,
    month DATE NOT NULL CHECK (isfinite(month) AND EXTRACT(DAY FROM month) = 1),
    average_fix NUMERIC NOT NULL,
    observed_days INTEGER NOT NULL CHECK (observed_days > 0),
    expected_days INTEGER NOT NULL CHECK (expected_days > 0),
    calendar_reference TEXT NOT NULL CHECK (btrim(calendar_reference) <> ''),
    source_run_id UUID NOT NULL REFERENCES ops.runs (run_id),
    calculated_at TIMESTAMPTZ NOT NULL CHECK (isfinite(calculated_at)),
    PRIMARY KEY (provider, series_code, month),
    FOREIGN KEY (provider, series_code) REFERENCES core.series (provider, series_code),
    CONSTRAINT fx_monthly_day_counts CHECK (observed_days = expected_days),
    CONSTRAINT fx_monthly_positive_finite CHECK (
        average_fix > 0 AND average_fix NOT IN ('NaN'::NUMERIC, 'Infinity'::NUMERIC, '-Infinity'::NUMERIC)
    )
);

-- Gold granos: las dependencias existen mediante FK. Sus valores, unidades y
-- fórmulas se comprobarán con las transformaciones y las reglas de publicación.
CREATE TABLE mart.grain_reference_monthly (
    provider TEXT NOT NULL,
    series_code TEXT NOT NULL,
    month DATE NOT NULL CHECK (isfinite(month) AND EXTRACT(DAY FROM month) = 1),
    fx_provider TEXT NOT NULL,
    fx_series_code TEXT NOT NULL,
    grain_price_usd_t NUMERIC NOT NULL,
    average_fix_mxn_usd NUMERIC NOT NULL,
    reference_mxn_t NUMERIC NOT NULL,
    mom_change_pct NUMERIC,
    yoy_change_pct NUMERIC,
    source_run_id UUID NOT NULL REFERENCES ops.runs (run_id),
    calculated_at TIMESTAMPTZ NOT NULL CHECK (isfinite(calculated_at)),
    PRIMARY KEY (provider, series_code, month),
    FOREIGN KEY (provider, series_code, month)
        REFERENCES core.observations (provider, series_code, observation_date),
    FOREIGN KEY (fx_provider, fx_series_code, month)
        REFERENCES mart.fx_monthly (provider, series_code, month),
    CONSTRAINT grain_reference_price_finite CHECK (
        grain_price_usd_t > 0
        AND grain_price_usd_t NOT IN ('NaN'::NUMERIC, 'Infinity'::NUMERIC, '-Infinity'::NUMERIC)
    ),
    CONSTRAINT grain_reference_fix_finite CHECK (
        average_fix_mxn_usd > 0
        AND average_fix_mxn_usd NOT IN ('NaN'::NUMERIC, 'Infinity'::NUMERIC, '-Infinity'::NUMERIC)
    ),
    CONSTRAINT grain_reference_value_finite CHECK (
        reference_mxn_t > 0
        AND reference_mxn_t NOT IN ('NaN'::NUMERIC, 'Infinity'::NUMERIC, '-Infinity'::NUMERIC)
    ),
    -- Las variaciones aceptan negativos, cero y NULL, pero no valores especiales.
    CONSTRAINT grain_reference_mom_finite CHECK (
        mom_change_pct IS NULL
        OR mom_change_pct NOT IN ('NaN'::NUMERIC, 'Infinity'::NUMERIC, '-Infinity'::NUMERIC)
    ),
    CONSTRAINT grain_reference_yoy_finite CHECK (
        yoy_change_pct IS NULL
        OR yoy_change_pct NOT IN ('NaN'::NUMERIC, 'Infinity'::NUMERIC, '-Infinity'::NUMERIC)
    )
);

-- El preparador no inserta watermarks. La carga histórica creará el primero
-- solo cuando confirme Silver, Gold y el estado de éxito en una publicación.
CREATE TABLE ops.watermarks (
    pipeline_name TEXT PRIMARY KEY CHECK (btrim(pipeline_name) <> ''),
    start_month DATE NOT NULL CHECK (isfinite(start_month) AND EXTRACT(DAY FROM start_month) = 1),
    published_through_month DATE NOT NULL
        CHECK (isfinite(published_through_month) AND EXTRACT(DAY FROM published_through_month) = 1),
    initial_run_id UUID NOT NULL REFERENCES ops.runs (run_id),
    last_run_id UUID NOT NULL REFERENCES ops.runs (run_id),
    updated_at TIMESTAMPTZ NOT NULL CHECK (isfinite(updated_at)),
    CONSTRAINT watermarks_interval CHECK (start_month <= published_through_month)
);
