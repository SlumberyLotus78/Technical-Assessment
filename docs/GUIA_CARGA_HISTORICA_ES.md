# Carga histórica inicial hasta Gold

## 1. Objetivo y periodo

La carga histórica reúne metadatos y observaciones de FRED y Banxico para un intervalo explícito, conserva Bronze, produce un perfil consolidado y utiliza el publicador transaccional para confirmar Silver, Gold y watermark.

El periodo definido para la carga es **enero de 2009 a septiembre de 2026**. Son 213 meses. El año 2009 aporta los comparadores anuales para analizar desde 2010, las primeras doce variaciones YoY de cada grano permanecen nulas por falta de un año anterior dentro del intervalo publicado.

El coordinador es inicial: requiere un producto sin watermark. Las actualizaciones posteriores utilizan el [comando incremental independiente](GUIA_CARGA_INCREMENTAL_ES.md). Las correcciones de periodos publicados utilizan el [comando de reproceso explícito](GUIA_RECUPERACION_Y_REPROCESOS_ES.md).

## 2. Archivos y responsabilidades

| Módulo | Responsabilidad |
|---|---|
| `clients/retry.py` | Política de intentos y espera ante fallos HTTP transitorios. |
| `clients/http.py` | Autenticación, consulta JSON, recursos de respuesta y errores controlados. |
| `sources/metadata.py` | Obtención del objeto nativo y validación reutilizable de metadatos. |
| `sources/windows.py` | División del intervalo en años calendario sin huecos ni solapamientos. |
| `sources/calendars/` | Referencias anuales bancarias revisadas de 2009 a 2026. |
| `quality/windows.py` | Meses cerrados, cuatro series conocidas, calendarios y disponibilidad declarada. |
| `extraction/captures.py` | Conservación de metadatos y de cada fragmento de observaciones. |
| `orchestration/extraction.py` | Consulta y registro de capturas compartidos con el incremental. |
| `orchestration/artifacts.py` | Manifiesto, perfil y resultado local de la ejecución. |
| `orchestration/failures.py` | Diagnóstico y cierre del intento fallido. |
| `orchestration/profiling.py` | Perfil de todas las observaciones reunidas por serie y cobertura FIX mensual. |
| `orchestration/historical.py` | Bloqueo desde la planificación, intento, extracción, archivos de evidencia y llamada al publicador. |

Se mantienen funciones con responsabilidades concretas y comentarios. No se añadieron clases de aplicación, dependencias ni migraciones SQL.

## 3. Calendarios y procedencia

Los recursos 2009–2025 se incorporaron a partir de la tabla pública curada del proyecto original, identificada por el commit `f641366`. Se conservó su fecha de revisión registrada, 2026-11-02. La copia de esa tabla, su SHA-256 y los hashes de cada recurso anual están en el [manifiesto de calendario histórico](evidencias/calendario_historico/manifest.json) y la [referencia previa](evidencias/calendario_historico/referencia_previa.csv).

Se consultaron los registros oficiales de publicación disponibles en SIDOF para cotejar sus fechas. Las referencias basadas en las ediciones del DOF de 2010-12-10, 2011-12-20 y 2014-12-29 conservan la procedencia de la revisión anterior. Las URLs primarias permanecen en cada JSON anual. No se presenta esa reutilización como una nueva lectura íntegra de todos los documentos.

Se preservaron los cierres extraordinarios del [17 de septiembre de 2010](https://sidof.segob.gob.mx/notas/5159251) y del [1 de octubre de 2024](https://sidof.segob.gob.mx/notas/5711052). Los feriados que caen en fin de semana no crean un traslado al lunes. El recurso 2026 previo permaneció intacto, con su mismo hash.

Las referencias producen 4,463 fechas FIX esperadas para el periodo elegido. Esa es una expectativa independiente de los datos recibidos, la carga debe contrastar sus observaciones con esas fechas. Un año sin referencia revisada bloquea la consulta de observaciones del histórico.

## 4. Ventanas anuales y reintentos

El intervalo se divide por año. La primera ventana empieza en 2009-01-01, la última termina en 2026-09-30. Las tres series mensuales FRED necesitan como máximo doce observaciones por ventana. Cada respuesta debe declarar una página completa, un conteo incompatible detiene la carga. La API documenta sus [controles de cantidad y desplazamiento](https://fred.stlouisfed.org/docs/api/fred/series_observations.html).

Para este periodo se planean cuatro consultas de metadatos y 72 de observaciones: 18 ventanas por cada una de las cuatro series. Son 76 consultas lógicas, los reintentos pueden aumentar el número de peticiones HTTP. Banxico recibe una consulta de metadatos y 18 históricas. Sus [límites oficiales](https://www.banxico.org.mx/SieAPIRest/service/v1/doc/limiteConsultas) distinguen ambas categorías.

El cliente permite hasta tres intentos GET, incluido el inicial. Reintenta timeouts, fallos de conexión transitorios y los estados 429, 500, 502, 503 y 504. Utiliza esperas exponenciales de uno y dos segundos cuando no existe una indicación válida del servidor.

`Retry-After` admite segundos o una fecha HTTP. Si exige más de 30 segundos, el cliente detiene la petición en lugar de repetirla antes de lo solicitado. Las respuestas se cierran antes de esperar. Errores de autenticación, TLS, contenido JSON o contratos de negocio no se reintentan como si fueran fallos temporales.

## 5. Recorrido de una ejecución

1. Valida el intervalo y adquiere el bloqueo del producto.
2. Comprueba esquema y catálogo, registra el intento y verifica que no exista un histórico publicado.
3. Consulta, conserva y registra los metadatos antes de exigir su contrato.
4. Comprueba que las cuatro fuentes y los calendarios cubran el periodo solicitado.
5. Consulta las ventanas anuales, guarda y registra cada respuesta antes de validar su estructura.
6. Consolida los perfiles y la cobertura FIX por mes.
7. Invoca el publicador, que repite sus verificaciones y confirma las capas, watermark y éxito juntos.

El bloqueo permanece adquirido desde la planificación. La conexión SQL queda sin transacción abierta mientras se realiza cada petición HTTP. Los registros de capturas se confirman progresivamente para conservar su trazabilidad ante un fallo posterior.

Un metadato incompatible queda archivado para diagnóstico. Si su envoltura no permite leer el registro nativo, se conserva el objeto recibido y el contrato posterior lo rechaza. Las respuestas de observaciones siempre se conservan completas antes de comprobar sus campos y conteos.

Los fallos de extracción se registran con su etapa y tipo de error. Si el publicador ya cerró un intento fallido, el coordinador histórico conserva ese cierre y su etapa real. La [guía de publicación](GUIA_PUBLICACION_GOLD_ES.md) detalla la reversión de las capas.

## 6. Archivos generados

Cada intento utiliza su propia carpeta:

```text
data/bronze/historical/<run_id>/
    metadata/                    Registros originales de las cuatro series
    observations/
        <fecha_inicio>_<fecha_fin>/
                                 Respuestas completas de cada ventana
    query_plan.json              Periodo y ventanas de consulta
    extraction_manifest.json     IDs, rutas y hashes registrados
    historical_profile.json      Perfiles por serie y cobertura mensual FIX
    publication_result.json      Métricas de una publicación confirmada
```

El perfil conserva rangos de fechas y valores, precisión de los números, ausencias, duplicados y cobertura. `fix_monthly_coverage` contiene la evaluación de calendario de cada mes, el perfil básico diario mantiene su significado de diagnóstico de filas. El perfil y el manifiesto preceden al commit de publicación.

`publication_result.json` se genera después del commit. Si falla únicamente esa exportación, el comando informa que la publicación quedó confirmada y remite al identificador durable en `ops.runs`.

## 7. Verificación realizada

La [evidencia de esta etapa](evidencias/carga_historica/validacion.json) registra **186 pruebas aprobadas: 133 sin servidor y 53 SQL**, con cero fallos, errores u omisiones. Diez casos nuevos de PostgreSQL recorrieron la carga histórica con HTTP simulado, también se verificaron ventanas, disponibilidad, conservación de respuestas y reintentos. La [validación final](VALIDACION_FINAL_ES.md) conserva el total posterior de la suite.

El caso del periodo completo utilizó precios ficticios de 100 USD/t y FIX ficticio de 20 MXN/USD. Escribió 639 precios y 4,463 FIX en Silver, 213 agregados FIX y 639 referencias Gold. Los valores MXN/t de ese caso son datos de prueba. Sus 76 respuestas simuladas validan el recorrido técnico, no acreditan una descarga nueva de observaciones reales.

Se verificaron interrupciones de red, metadatos incompatibles, páginas FRED truncadas, FIX incompleto, años sin calendario y fallos de publicación. También se ejecutó el comando de terminal con un archivo de configuración ficticio y una base desechable. La instancia temporal PostgreSQL 18.6 se detuvo al terminar. No se leyó el `.env` real ni se escribió en la base del proyecto.

## 8. Ejecución con las APIs reales

Desde la raí del repositorio, con `.venv` activado y las variables privadas ya configuradas, comprobar la base y ejecutar las pruebas:

```powershell
python -X utf8 -m grain_pipeline.persistence.initialize --env-file .env --check-only
python -X utf8 -m tests.run --postgres --env-file .env
```

`DATABASE_URL` identifica la base del producto, `TEST_DATABASE_URL` identifica la conexión de pruebas. La carga necesita además `FRED_API_KEY` y `BANXICO_TOKEN`.

En una base del proyecto aún sin watermark, ejecutar la inicialización histórica elegida:

```powershell
python -X utf8 -m grain_pipeline.orchestration.historical --start-month 2009-01 --end-month 2026-09 --env-file .env
```

Este comando consulta las APIs y escribe en la base indicada por `DATABASE_URL`. En una primera carga completa y correcta, las métricas esperadas son 5,102 observaciones Silver, 213 meses FIX y 639 referencias Gold. Esa ejecución real ya se confirmó en la base del proyecto, allí se debe continuar con el incremental o el reproceso, sin repetir la inicialización histórica. El resultado de otra instalación depende de su propia ejecución y sus verificaciones.

En pgAdmin se puede comprobar:

```sql
SELECT run_id, load_type, status, stage, start_month, end_month
FROM ops.runs ORDER BY started_at DESC LIMIT 5;

SELECT provider, series_code, count(*) AS observations
FROM core.observations GROUP BY provider, series_code ORDER BY provider, series_code;

SELECT count(*) AS fx_months FROM mart.fx_monthly;
SELECT count(*) AS grain_references FROM mart.grain_reference_monthly;
SELECT * FROM ops.watermarks;
```

Después de revisar el resultado, guardar el avance:

```powershell
git status --short
git add README.MD grain_pipeline tests docs
git diff --cached --stat
git commit -m "feat: add explicit historical extraction through Gold"
git status
```

## 9. Continuidad

Se confirmó posteriormente la ejecución histórica real con los resultados esperados. La [guía incremental](GUIA_CARGA_INCREMENTAL_ES.md) documenta las actualizaciones, su revisión configurable y la verificación ampliada. Los módulos comunes de captura y disponibilidad se renombraron al incorporar esa segunda carga, la interfaz y los archivos del histórico se conservaron. La [recuperación de intentos interrumpidos](GUIA_RECUPERACION_Y_REPROCESOS_ES.md) y el [wheel para automatización](GUIA_AUTOMATIZACION_ES.md) también están implementados.
