# Análisis de granos y FIX conectado a PostgreSQL

## 1. Pregunta y alcance

El dashboard permite explorar cómo se combinan el precio internacional de maíz, trigo y soya con el FIX para formar una referencia mensual nominal en MXN por tonelada. Utiliza exclusivamente la publicación Gold confirmada por el watermark. La interpretación considera que esta referencia excluye fletes, seguros, aranceles, calidad y otras condiciones comerciales.

La relación es matemática. Una asociación visual o una contribución calculada no demuestra causalidad económica. Los hallazgos se calculan para el periodo y el grano seleccionados, sin incorporar precios futuros ni completar meses ausentes.

## 2. Tres visualizaciones

| Vista | Qué responde | Unidad y base |
|---|---|---|
| Evolución internacional y en pesos | ¿Cuánto cambió cada referencia respecto del inicio visible? | Índices USD/t y MXN/t, base 100 en el primer mes seleccionado. |
| Contribuciones mensuales | ¿Qué parte del cambio mensual corresponde al precio internacional y al FIX? | MXN/t o puntos porcentuales respecto de la referencia del mes calendario previo. |
| Comparación entre granos | ¿Cómo difiere la variación acumulada en pesos dentro del mismo periodo? | Porcentaje entre primera y última referencia visible, con los mismos meses para los tres granos. |

La interfaz incluye selección mensual de inicio y fin, selección de grano, referencia y FIX del último mes, cambio acumulado, hallazgos de la selección y detalle de cobertura. Un periodo de un solo mes tiene cambio acumulado cero, puede tener contribución mensual si existe el mes previo publicado.

## 3. Indicadores y atribución

La referencia mensual se toma de Gold: `R = P × F`, con `P` en USD/t y `F` como promedio FIX del mes en MXN/USD. El índice visible se calcula como `100 × valor actual / valor inicial`.

Para repartir el cambio de una multiplicación sin asignar toda la interacción a un solo factor, se utiliza una atribución simétrica:

```text
Contribución del precio = (P_actual − P_previo) × (F_actual + F_previo) / 2
Contribución del FIX    = (F_actual − F_previo) × (P_actual + P_previo) / 2
Suma                   = R_actual − R_previo
```

La versión en puntos porcentuales divide cada contribución entre `R_previo` y multiplica por cien. La reconciliación se interpreta dentro de la precisión decimal de cálculo: 34 dígitos significativos y `ROUND_HALF_EVEN`. La conversión a `float` ocurre únicamente al presentar gráficos y tablas.

El comparador es el mes calendario inmediatamente anterior en el histórico publicado. Puede quedar fuera del filtro visible, la interfaz explica ese alcance. Cuando falta por tratarse del inicio del producto, las contribuciones son nulas. Las variaciones YoY también conservan su comparador exacto publicado, sin convertir una ausencia en cero.

**Ahorro cancelado** identifica un mes con caída del precio USD/t y referencia MXN/t igual o mayor a la del mes previo. Su frecuencia utiliza como denominador únicamente meses comparables con caída internacional. Si no existen, la frecuencia queda nula. Los meses sin comparador se muestran por separado.

Los textos de mayor y menor variación se derivan de la selección actual. Una subida del FIX significa más MXN por USD y puede compensar una caída internacional, su efecto concreto depende de ambos valores observados.

## 4. Consulta y controles

`app/queries.py` lee el watermark y Gold en una transacción `REPEATABLE READ, READ ONLY`. Así una publicación concurrente no combina el watermark de una versión con resultados de otra. Se establecen esperas máximas de conexión, consulta y bloqueo. El comportamiento está definido por [SET TRANSACTION de PostgreSQL](https://www.postgresql.org/docs/18/sql-set-transaction.html).

Antes de mostrar resultados se comprueba que existan los tres granos para cada mes, con valores positivos y finitos, FIX compartido y cobertura certificada. Se concilian producto y variaciones. Una inconsistencia se informa mediante un error controlado, el dashboard no publica ni repara datos. La procedencia Bronze se verifica durante las cargas, la interfaz no requiere acceso a esos archivos.

| Archivo | Responsabilidad |
|---|---|
| `app/queries.py` | Conexión e instantánea de solo lectura. |
| `grain_pipeline/quality/analytics.py` | Contrato del producto analítico publicado. |
| `app/analytics.py` | Índices, atribución, frecuencias y hallazgos con `Decimal`. |
| `app/charts.py` | Gráficos y conversión numérica para presentación. |
| `app/streamlit_app.py` | Filtros, indicadores, textos y tablas. |
| `.streamlit/config.toml` | Tema visual y desactivación de estadísticas de uso. |

Se fijaron Streamlit 1.66.1 y Plotly 7.1.0 en `requirements.txt`, comprobando sus distribuciones en [PyPI Streamlit](https://pypi.org/project/streamlit/1.66.1/) y [PyPI Plotly](https://pypi.org/project/plotly/7.1.0/).

## 5. Ejecutar y preparar una cuenta de lectura

Con el entorno virtual activo y el histórico publicado:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app/streamlit_app.py --server.address 127.0.0.1
```

Abrir `http://localhost:8501`. La configuración privada utiliza `READONLY_DATABASE_URL` cuando está definida, si falta esa clave, utiliza `DATABASE_URL` y fuerza igualmente solo lectura. Una clave definida pero vacía exige corregirse. No se requieren llaves de APIs para consultar el dashboard.

Para una cuenta independiente, crear en pgAdmin un rol de acceso llamado, por ejemplo, `grain_reader`, con contraseña privada y sin privilegios de administración. Después, desde la base del proyecto y con una cuenta autorizada, conceder:

```sql
GRANT CONNECT ON DATABASE fred_banxico TO grain_reader;
GRANT USAGE ON SCHEMA core, mart, ops TO grain_reader;
GRANT SELECT ON core.series,
    mart.fx_monthly, mart.grain_reference_monthly,
    ops.watermarks, ops.runs, ops.schema_migrations TO grain_reader;
```

Sustituir el nombre de la base si esta rama utiliza otro. Agregar la conexión únicamente al `.env` local:

```dotenv
READONLY_DATABASE_URL=postgresql://grain_reader:YOUR_PASSWORD@localhost:5432/fred_banxico
```

`GRAIN_ENV_FILE` permite seleccionar otra ruta privada. No se almacena la conexión en el caché de Streamlit ni se incluye en errores de PostgreSQL. Cada interacción consulta una instantánea nueva, el botón de actualización permite solicitarla conservando los filtros vigentes.

## 6. Verificación y evidencia

La [evidencia conjunta](evidencias/recuperacion_dashboard/validacion.json) registra la suite y las versiones utilizadas. Las pruebas comprobaron las identidades numéricas, el denominador de cancelaciones, filtros, unidades, selección de un mes, errores sin credenciales y ejecución de la interfaz sobre consultas reales a PostgreSQL aislado. También verificaron una cuenta con permisos únicamente de lectura, rechazo de DML incluso con una cuenta administradora y estabilidad de la instantánea durante una publicación concurrente.

Las pruebas SQL utilizaron bases desechables y entradas HTTP ficticias. No se leyeron las credenciales locales ni se consultaron las APIs reales. Los valores de esas pruebas no se presentan como hallazgos económicos del histórico real. La muestra real previamente archivada y sus resultados originales permanecen en el [perfilamiento inicial](Perfilamiento_inicial.md) y la [vista previa Gold](evidencias/calendario_gold/vista_previa.json).

La revisión visual en navegador no se completó: Computer Use detuvo la interacción al no poder identificar con suficiente confianza la URL actual de Windows. El [registro de revisión](evidencias/recuperacion_dashboard/revision_interfaz.json) distingue esa limitación de la aprobación de AppTest. El servidor de vista previa y el clúster temporal se detuvieron, y su base ficticia se retiró.

Se confirmó posteriormente el funcionamiento y la apariencia de la aplicación conectada a la base del proyecto. El cierre incorporó una lectura real de Gold y [resultados sustentados](RESULTADOS_ANALISIS_ES.md).
