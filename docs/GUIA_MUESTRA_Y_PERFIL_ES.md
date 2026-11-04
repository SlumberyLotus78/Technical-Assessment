# Guía de lectura: descarga de muestra y perfil de observaciones

## 1. Qué construimos y por qué

El avance anterior preparó las ventanas de consulta. Ahora descargamos las observaciones de esos periodos, conservamos las respuestas y revisamos sus registros. Este diagnóstico corresponde a la exploración de fuentes del plan de implementación.

Las muestras permitieron estudiar el formato de los datos y probar las primeras reglas antes de definir la carga histórica. El diagnóstico se mantiene separado de los comandos de [histórico](GUIA_CARGA_HISTORICA_ES.md) e [incremental](GUIA_CARGA_INCREMENTAL_ES.md), ya implementados hasta Gold. Una muestra no inicializa el watermark del producto.

El recorrido es:

```text
Metadatos -> Ventanas -> Consulta de observaciones -> Captura JSON
                                                        |
                                                        v
                                                  Contrato -> Perfil
```

La captura precede al contrato de observaciones. Si cambia la estructura de una respuesta, podremos inspeccionar el objeto recibido.

## 2. Archivos y responsabilidades

| Archivo | Responsabilidad |
|---|---|
| `sources/observations.py` | Elegir el endpoint, consultar y leer la estructura de cada proveedor. |
| `sources/sampling.py` | Reutilizar la selección de mes y las ventanas del avance anterior. |
| `quality/values.py` | Interpretar números y marcadores ausentes. |
| `quality/profiling.py` | Aplicar controles y resumir incidencias de las observaciones. |
| `extraction/raw.py` | Crear una carpeta de ejecución y conservar documentos JSON. |
| `extraction/sample.py` | Coordinar los pasos y ofrecer el comando de diagnóstico. |

`quality` y `extraction` tienen sus propios `__init__.py`, igual que los paquetes que ya conocimos. Las funciones de calidad reciben datos, pueden probarse sin red, configuración privada ni PostgreSQL.

La constante `OPERATING_TIMEZONE` pasó a `common/dates.py`: la consulta de metadatos y la muestra comparten la misma zona de operación.

## 3. Cómo consultamos las observaciones

FRED utiliza `series/observations`, fechas ISO y el código en `series_id`. Se solicitan niveles mediante `units=lin`, `output_type=1` y orden ascendente. La respuesta incluye los registros y los controles `count`, `offset` y `limit`. [Contrato de FRED](https://fred.stlouisfed.org/docs/api/fred/series_observations.html).

La muestra cabe en una página. Exigimos que el total declarado coincida con los registros recibidos y que el desplazamiento sea cero. Una página parcial produce un error. Las cargas dividen sus consultas por año calendario y exigen una respuesta completa por ventana, no se implementó un paginador genérico.

Banxico utiliza `series/{codigo}/datos/{inicio}/{fin}` con fechas ISO en la petición. La respuesta agrupa `datos` dentro de una serie y utiliza `fecha` y `dato` para sus registros. [Consulta por rango](https://www.banxico.org.mx/SieAPIRest/service/v1/doc/consultaDatosSerieRango), [ejemplo oficial de respuesta](https://www.banxico.org.mx/SieAPIRest/service/v1/).

`fetch_observations` devuelve el objeto JSON completo. `read_observations` comprueba la envoltura y crea una lista con los nombres comunes `date` y `value`, conservando los textos de origen. En Banxico también verifica el identificador de la serie. La respuesta FRED de observaciones no incluye ese identificador, el contexto conserva el código solicitado y la consulta previa valida sus metadatos.

Un campo ausente representa una estructura incompatible y detiene el diagnóstico. Un campo presente con una fecha o valor incorrectos se cuenta en el perfil.

## 4. Qué conservamos en la carpeta de ejecución

La carpeta raíz predeterminada es `data/bronze/samples/`. Cada ejecución crea un subdirectorio nuevo, con hora UTC e identificador único:

```text
data/bronze/samples/<ejecucion>/
    fred_PMAIZMTUSDM_metadata.json
    fred_PMAIZMTUSDM_observations.json
    fred_PWHEAMTUSDM_metadata.json
    fred_PWHEAMTUSDM_observations.json
    fred_PSOYBUSDM_metadata.json
    fred_PSOYBUSDM_observations.json
    banxico_SF43718_metadata.json
    banxico_SF43718_observations.json
    profile.json
```

Las capturas incluyen proveedor, código, tipo de captura, instante UTC y ventana consultada. `payload` contiene el registro validado de metadatos o el objeto completo de observaciones, según el archivo.

Conservamos el contenido JSON interpretado, con formato legible. Esta captura no conserva los bytes exactos del cuerpo HTTP. Los números entregados como texto permanecen como texto, incluidos sus decimales y marcadores ausentes.

Los archivos se crean con modo `x`: Python rechaza reemplazar un archivo existente. Las credenciales y las URLs preparadas por `requests` quedan fuera del contexto que construimos. `.gitignore` excluye `/data/`, las capturas locales se generan al ejecutar el código.

La evidencia seleccionada del primer diagnóstico real tiene una copia versionable en `docs/evidencias/perfilamiento_inicial/`, vinculada desde el [informe de resultados](Perfilamiento_inicial.md). Las capturas operativas originales permanecen en `/data/`.

`profile.json` se escribe cuando las cuatro series completan sus contratos y perfiles. Si falla una consulta o estructura, permanecen las capturas previas y el comando termina como diagnóstico incompleto. Una interrupción durante la escritura también puede dejar un archivo parcial, una carpeta sin perfil final no acredita la terminación del diagnóstico.

## 5. Por qué utilizamos Decimal

El texto `"100.1234567890123456789"` se convierte directamente con `Decimal`. Así conservamos sus dígitos sin pasar por un `float` binario. `Decimal` es un tipo de la biblioteca estándar y se usa aquí como representación del número. [Documentación de Decimal](https://docs.python.org/3.12/library/decimal.html).

Las reglas iniciales de `quality/values.py` son explícitas:

- `None`, texto vacío y `.` se consideran ausentes para FRED.
- `None`, texto vacío, `N/E` y `N/D` se consideran ausentes para Banxico.
- Se acepta texto decimal con signo opcional. Banxico también admite comas de miles con grupos completos de tres dígitos.
- Un texto desconocido, notación científica, comas mal agrupadas o un tipo distinto de texto se cuentan como inválidos.
- Cero y negativos se interpretan como números y se cuentan mediante la regla de positividad del perfil.

Por ejemplo, `1,234.50` de Banxico puede interpretarse como `1234.50`, `18,75` se registra como inválido. Las observaciones reales permitirán contrastar estas reglas, un formato nuevo quedará visible como incidencia.

## 6. Cómo leer el perfil

| Campo | Significado |
|---|---|
| `rows` | Cantidad de registros recibidos. |
| `numeric_values` | Cantidad de valores interpretables como número, incluidos cero y negativos. |
| `missing_values` | Valores ausentes según las reglas anteriores. |
| `invalid_values` | Tipos o formatos numéricos incompatibles. |
| `non_positive_values` | Valores numéricos menores o iguales a cero. |
| `invalid_dates` | Textos de fecha que no cumplen el formato o el calendario. |
| `outside_window` | Fechas interpretables fuera de la ventana consultada. |
| `non_month_start_dates` | Fechas mensuales cuyo día es distinto de uno. |
| `duplicate_dates` | Apariciones adicionales de una misma fecha. |
| `observed_start`, `observed_end` | Extremos de las fechas interpretables recibidas. |
| `value_min`, `value_max` | Extremos de los valores numéricos, guardados como texto exacto. |
| `expected_months`, `missing_months` | Periodos mensuales esperados y meses sin un valor positivo con fecha correcta. |
| `has_issues` | Indica filas vacías o alguna incidencia en las reglas implementadas. |

Los contadores son independientes: una fila puede tener una fecha incorrecta y un valor ausente. No deben sumarse como si fueran grupos de filas excluyentes. El perfil conserva y describe los problemas, no elimina, rellena ni corrige registros.

Para FRED comprobamos la presencia de los meses de la ventana. Los duplicados siguen siendo incidencia aunque exista un valor positivo para el mes.

Para FIX, `coverage_status` queda en `pending_banking_calendar`. Un perfil sin incidencias en sus registros todavía requiere comprobar el calendario hábil bancario para acreditar la cobertura diaria completa. La [regla mensual DQ-09](GUIA_CALENDARIO_Y_GOLD_ES.md) realiza esa comprobación en la vista previa Gold y en las cargas. El perfil inicial conserva su resultado de diagnóstico.

## 7. Pruebas realizadas y comprobación real

En esta etapa se añadieron 23 casos a los 40 anteriores. La suite local ejecutó los **63 casos** y terminó con `OK`. Se comprobaron parámetros, contratos, precisión, ausentes, fechas, duplicados, conservación de capturas, interrupciones y el código de salida por incidencias. La [validación final](VALIDACION_FINAL_ES.md) conserva el recuento de la suite completa posterior.

Las respuestas fueron ficticias y las capturas de prueba se escribieron en carpetas temporales. Esta ejecución no leyó las claves reales del proyecto ni descargó sus observaciones. La ayuda del comando también se comprobó localmente.

Se confirmó que el diagnóstico real anterior de fechas y ventanas finalizó correctamente, ese avance quedó en `89303ae`. La muestra real posterior contiene 30 observaciones y sus cuatro perfiles se reprodujeron desde las capturas. El [perfilamiento inicial](Perfilamiento_inicial.md) documenta los resultados, su evidencia y los límites de cobertura.

## 8. Ejecutar el diagnóstico de muestra

Desde la raí del repositorio, con el entorno virtual activado:

```powershell
python -X utf8 -m grain_pipeline.extraction.sample --env-file .env
```

La ejecución hace cuatro consultas de metadatos y cuatro de observaciones. El mes se elige con la disponibilidad consultada y la fecha de operación. Para repetir un periodo explícito que cumpla las mismas reglas:

```powershell
python -X utf8 -m grain_pipeline.extraction.sample --env-file .env --month 2026-09
```

Septiembre es un ejemplo de argumento. El comando comprobará su disponibilidad al ejecutarse. La salida muestra la carpeta, el mes y los conteos reales, no hay un número fijo de observaciones diarias.

Cuando las reglas actuales no detectan incidencias, termina con:

```text
Muestra descargada e inspeccionada: 4 series.
```

El código de salida es cero en ese caso y uno ante incidencias o un diagnóstico incompleto. En PowerShell puede consultarse con `$LASTEXITCODE` inmediatamente después del comando. Si existen incidencias, revisar los contadores de `profile.json`, si falló un contrato, revisar la captura correspondiente.

Para abrir el perfil más reciente:

```powershell
$sampleRun = Get-ChildItem -LiteralPath data/bronze/samples -Directory |
    Sort-Object Name -Descending |
    Select-Object -First 1
Get-Content -LiteralPath (Join-Path $sampleRun.FullName 'profile.json') -Encoding utf8
```

Este ejemplo supone que el último diagnóstico terminó y escribió su perfil. Si quedó incompleto, la terminal ya muestra la carpeta donde permanecieron sus capturas.

La suite del checkout puede ejecutarse con:

```powershell
python -X utf8 -m unittest discover -s tests -v
```

Este comando no carga `.env`, los casos SQL se omiten si no existe `TEST_DATABASE_URL` en el entorno. La [guía PostgreSQL](GUIA_POSTGRESQL_ES.md) explica cómo ejecutar la integración explícita.

## 9. Guardar el avance

Después de comprobar la muestra real sin incidencias:

```powershell
git add .gitignore README.MD grain_pipeline tests docs
git diff --cached --stat
git commit -m "feat: capture and profile source observation samples"
git status
```

Las capturas operativas quedan en la carpeta local ignorada. El commit conserva el código, las reglas, las pruebas, esta explicación y la evidencia inicial seleccionada en `docs`. El diseño derivado de esta exploración se encuentra en el [modelo de datos](MODELO_DATOS_ES.md), el [diccionario](DICCIONARIO_DATOS_ES.md) y el [catálogo DQ](REGLAS_CALIDAD_ES.md).
