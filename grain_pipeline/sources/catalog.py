"""Catálogo inicial de series y metadatos esperados."""

# Las tres series de granos comparten unidad, frecuencia y tratamiento estacional.
# Guardar esta definición una vez permite reutilizarla en sus tres entradas.
FRED_GRAIN_METADATA = {
    "units": "U.S. Dollars per Metric Ton",
    "frequency": "Monthly",
    "frequency_short": "M",
    # NSA significa que la serie no está ajustada estacionalmente.
    "seasonal_adjustment_short": "NSA",
}

# Los nombres de los campos de Banxico son distintos a los de FRED.
BANXICO_FIX_METADATA = {
    "unidad": "Pesos por Dólar",
    "periodicidad": "Diaria",
    "cifra": "Tipo de Cambio",
}

SERIES = (
    # Primera serie: precio internacional del maíz.
    {
        # Proveedor al que corresponderá la consulta.
        "provider": "FRED",
        # Identificador oficial de la serie, distinto de su nombre descriptivo.
        "code": "PMAIZMTUSDM",
        # Nombre que utilizamos dentro del proyecto para identificar el dato.
        "name": "Maíz",
        # Unidad esperada: dólares estadounidenses por tonelada métrica.
        "unit": "USD/t",
        # Frecuencia esperada: una observación por mes.
        "frequency": "monthly",
        # Título esperado de esta serie en los metadatos del proveedor.
        "source_title": "Global price of Corn",
        # Referencia a los campos esperados compartidos por los tres granos.
        "expected_metadata": FRED_GRAIN_METADATA,
    },
    # Segunda serie: trigo. Reutiliza los mismos campos del primer diccionario.
    {
        "provider": "FRED",
        "code": "PWHEAMTUSDM",
        "name": "Trigo",
        "unit": "USD/t",
        "frequency": "monthly",
        "source_title": "Global price of Wheat",
        "expected_metadata": FRED_GRAIN_METADATA,
    },
    # Tercera serie: soya, también con precio mensual en USD por tonelada métrica.
    {
        "provider": "FRED",
        "code": "PSOYBUSDM",
        "name": "Soya",
        "unit": "USD/t",
        "frequency": "monthly",
        "source_title": "Global price of Soybeans",
        "expected_metadata": FRED_GRAIN_METADATA,
    },
    # Cuarta serie: FIX de determinación de Banxico, expresado en MXN por USD.
    # daily indica frecuencia diaria; el calendario de publicación se evaluará
    # al validar la cobertura, considerando los días hábiles bancarios.
    {
        "provider": "Banxico",
        "code": "SF43718",
        "name": "FIX",
        "unit": "MXN/USD",
        "frequency": "daily",
        # Este componente identifica la fecha de determinación FIX en su título.
        "source_title": "Fecha de determinación (FIX)",
        "expected_metadata": BANXICO_FIX_METADATA,
    },
)
