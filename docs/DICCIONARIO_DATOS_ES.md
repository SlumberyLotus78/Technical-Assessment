# Diccionario del modelo de datos

## 1. Alcance y convenciones

Este diccionario especifica las ocho tablas del [modelo de datos](MODELO_DATOS_ES.md) y la tabla técnica de versiones. El SQL inicial conserva su checksum. Se confirmó la preparación de la base y la ejecución histórica real. Los comandos histórico e incremental integran extracción y publicador con las comprobaciones del [catálogo DQ](REGLAS_CALIDAD_ES.md). Las ejecuciones con fuentes reales se distinguen de las pruebas técnicas con HTTP simulado.

`PK` identifica una clave primaria y `FK` una relación con otra tabla. Los componentes de una clave compuesta se interpretan juntos. Los identificadores `UUID` corresponden a ejecuciones, capturas y verificaciones técnicas, los códigos de las fuentes conservan su valor público original.

Los campos son obligatorios salvo que la columna «Admite NULL» indique lo contrario. `NUMERIC` representa valores decimales sin escala forzada, los instantes usan `TIMESTAMPTZ`. Los nombres de estado y de etapa constituyen valores del contrato de aplicación, reforzados por restricciones SQL.

## 2. core.series

**Granularidad:** una serie por proveedor. **PK:** `(provider, series_code)`.

| Campo | Tipo | Admite NULL | Significado |
|---|---|---|---|
| `provider` | `TEXT` | No | Proveedor del catálogo: `FRED` o `Banxico`. |
| `series_code` | `TEXT` | No | Código oficial, por ejemplo `PMAIZMTUSDM` o `SF43718`. |
| `name` | `TEXT` | No | Nombre interno: Maíz, Trigo, Soya o FIX. |
| `unit` | `TEXT` | No | Unidad interna validada: `USD/t` o `MXN/USD`. |
| `frequency` | `TEXT` | No | `monthly` o `daily`, según el catálogo. |
| `source_title` | `TEXT` | No | Título o componente de título esperado para validar la serie. |
| `expected_metadata` | `JSONB` | No | Campos y valores del contrato de metadatos del proveedor. |

La tabla se inicializa con el catálogo existente. Cambiar una unidad o frecuencia requiere revisar su contrato y sus observaciones, la sincronización del catálogo rechaza diferencias y conserva las definiciones publicadas.

## 3. ops.runs

**Granularidad:** un intento de carga. **PK:** `run_id`.

| Campo | Tipo | Admite NULL | Significado |
|---|---|---|---|
| `run_id` | `UUID` | No | Identificador de la ejecución. |
| `load_type` | `TEXT` | No | `historical` o `incremental`, el reproceso utiliza `historical` y se distingue por `CTL-05.operation`, la recuperación conserva la modalidad de su origen en un intento nuevo. |
| `status` | `TEXT` | No | `running`, `succeeded`, `failed` o `skipped`. |
| `stage` | `TEXT` | No | Etapa actual o final: `planning`, `extraction`, `quality`, `silver`, `gold` o `publication`. |
| `start_month` | `DATE` | Sí | Primer mes del intervalo a procesar, incluyendo revisión de periodos anteriores. Nulo durante la planificación incremental previa a seleccionar la ventana y en cierres sin trabajo. |
| `end_month` | `DATE` | Sí | Último mes del intervalo a procesar. |
| `started_at` | `TIMESTAMPTZ` | No | Inicio del intento. |
| `finished_at` | `TIMESTAMPTZ` | Sí | Fin del intento, obligatorio en estados terminales. |
| `error_summary` | `TEXT` | Sí | Mensaje controlado, obligatorio cuando el estado sea `failed`. |

Los meses se completan al determinar un intervalo. Ambos pueden permanecer nulos durante la planificación o si el intento termina sin trabajo, cuando existen deben estar presentes juntos, ser primeros de mes y cumplir `start_month <= end_month`. Una publicación satisfactoria exige un intervalo definido. `finished_at` debe ser posterior o igual a `started_at`.

## 4. ops.raw_captures

**Granularidad:** una captura de origen. **PK:** `capture_id`. **Unicidad adicional:** `storage_path`.

| Campo | Tipo | Admite NULL | Significado |
|---|---|---|---|
| `capture_id` | `UUID` | No | Identificador técnico de la captura. |
| `run_id` | `UUID` | No | FK a `ops.runs.run_id`. |
| `provider`, `series_code` | `TEXT`, `TEXT` | No | FK compuesta a `core.series`. |
| `kind` | `TEXT` | No | `metadata` u `observations`. |
| `storage_path` | `TEXT` | No | Ruta relativa del archivo dentro del almacenamiento Bronze. |
| `content_sha256` | `TEXT` | No | SHA-256 del archivo: 64 caracteres hexadecimales. |
| `captured_at` | `TIMESTAMPTZ` | No | Instante de captura de la respuesta. |
| `window_start`, `window_end` | `DATE`, `DATE` | Sí | Ventana solicitada, ambos obligatorios y ordenados para observaciones, ambos nulos para metadatos. |

El archivo debe existir y coincidir con su hash antes de considerarlo una entrada válida. Las respuestas de observaciones se conservan antes de validar su contenido. Los metadatos conservan el registro nativo recibido con sus textos, si no se puede obtener ese registro, la carga archiva el objeto incompatible para diagnóstico y rechaza su contrato. El hash identifica los bytes del archivo Bronze, que contiene JSON interpretado, no el cuerpo HTTP original.

Las funciones de registro comparan el hash y el contexto de una ruta existente. Una reutilización conserva el ID y la ejecución de captura originales, un archivo revisado debe tener una ruta nueva. Las rutas se interpretan respecto de la misma raíz Bronze configurada para la base.

## 5. core.observations

**Granularidad:** una observación vigente. **PK:** `(provider, series_code, observation_date)`.

| Campo | Tipo | Admite NULL | Significado |
|---|---|---|---|
| `provider`, `series_code` | `TEXT`, `TEXT` | No | FK compuesta a `core.series`. |
| `observation_date` | `DATE` | No | Periodo mensual FRED o fecha diaria FIX. |
| `value` | `NUMERIC` | No | Valor finito y positivo, en la unidad del catálogo. |
| `source_capture_id` | `UUID` | No | FK a `ops.raw_captures.capture_id`, captura que sustenta el valor vigente. |
| `created_run_id` | `UUID` | No | FK a `ops.runs.run_id`, primera inserción. |
| `updated_run_id` | `UUID` | No | FK a `ops.runs.run_id`, última inserción o modificación del valor. |
| `created_at` | `TIMESTAMPTZ` | No | Instante de primera inserción. |
| `updated_at` | `TIMESTAMPTZ` | No | Instante de inserción o última modificación. |

La preparación Silver comprueba que la fecha de una serie mensual sea el primer día del mes. La escritura exige catálogo compatible, hash y contexto coincidentes, captura de observaciones e intervalo contenido en el intento planificado. La FK a `source_capture_id` por sí sola no acredita esas coincidencias.

Ante una revisión se conservan `created_run_id` y `created_at`, y se actualizan valor, captura y campos de modificación. Una observación sin cambios conserva su fila y procedencia vigentes, el nuevo intento y su captura quedan en `ops`.

## 6. ops.dq_results

**Granularidad:** la evaluación de una regla sobre un alcance de una ejecución. **PK:** `dq_result_id`.

| Campo | Tipo | Admite NULL | Significado |
|---|---|---|---|
| `dq_result_id` | `UUID` | No | Identificador de la evaluación. |
| `run_id` | `UUID` | No | FK a `ops.runs.run_id`. |
| `rule_code` | `TEXT` | No | Identificador estable del catálogo DQ. |
| `provider`, `series_code` | `TEXT`, `TEXT` | Sí | FK compuesta a `core.series`, ambos nulos para controles del producto completo. |
| `period_start`, `period_end` | `DATE`, `DATE` | No | Intervalo de la evaluación, con inicio anterior o igual a fin. |
| `status` | `TEXT` | No | `passed`, `failed` o `pending`. |
| `details` | `JSONB` | No | Métricas, fechas afectadas y referencias de evidencia según la regla. |
| `checked_at` | `TIMESTAMPTZ` | No | Instante de evaluación. |

Las evaluaciones describen su alcance: por ejemplo, una serie en un mes o las dependencias de todo el producto. Los decimales que aparecen dentro de `details` se representan como texto. Los resultados de una ejecución anterior se conservan para la auditoría del intento.

La persistencia del perfil recalcula las métricas desde la captura registrada y guarda los códigos aplicables con su ID de captura en `details`. El perfil básico por captura deja DQ-09 en `pending`, el publicador omite ese pendiente de diagnóstico y registra la evaluación bancaria mensual con su resultado efectivo. Una cobertura obligatoria fallida o pendiente bloquea Gold. Las reglas DQ-07 y DQ-08, exclusivas de series mensuales, no se aplican al FIX diario.

## 7. mart.fx_monthly

**Granularidad:** un mes certificado de una serie FIX. **PK:** `(provider, series_code, month)`.

| Campo | Tipo | Admite NULL | Significado |
|---|---|---|---|
| `provider`, `series_code` | `TEXT`, `TEXT` | No | FK compuesta a `core.series`, serie diaria FIX validada en MXN/USD. |
| `month` | `DATE` | No | Primer día del mes agregado. |
| `average_fix` | `NUMERIC` | No | Media FIX finita y positiva bajo la política decimal del modelo. |
| `observed_days` | `INTEGER` | No | Número de fechas FIX válidas y distintas del mes. |
| `expected_days` | `INTEGER` | No | Número de fechas del calendario bancario aplicable. |
| `calendar_reference` | `TEXT` | No | Versión y SHA-256 del recurso bancario anual utilizado, con saltos de línea normalizados. |
| `source_run_id` | `UUID` | No | FK a `ops.runs.run_id`, ejecución que produjo el agregado vigente. |
| `calculated_at` | `TIMESTAMPTZ` | No | Instante de cálculo. |

Los conteos deben ser positivos e iguales. La certificación exige además igualdad de conjuntos de fechas y aprobación de los controles del mes. Las referencias revisadas cubren 2009–2026, cualquier año adicional requiere su propia evidencia. La persistencia añade ejecución e instante de cálculo dentro de la publicación y conserva la fila si ninguno de sus campos analíticos cambia.

## 8. mart.grain_reference_monthly

**Granularidad:** una referencia mensual vigente por grano. **PK:** `(provider, series_code, month)`.

| Campo | Tipo | Admite NULL | Significado |
|---|---|---|---|
| `provider`, `series_code` | `TEXT`, `TEXT` | No | Identificación de la serie mensual del grano en USD/t. |
| `month` | `DATE` | No | Primer día del periodo. Junto con proveedor y serie, FK a `core.observations`. |
| `fx_provider`, `fx_series_code` | `TEXT`, `TEXT` | No | Identificación de la serie FIX usada. Junto con `month`, FK a `mart.fx_monthly`. |
| `grain_price_usd_t` | `NUMERIC` | No | Precio de origen finito y positivo utilizado para el cálculo. |
| `average_fix_mxn_usd` | `NUMERIC` | No | Media FIX certificada utilizada para el cálculo. |
| `reference_mxn_t` | `NUMERIC` | No | Producto finito y positivo de las dos entradas anteriores. |
| `mom_change_pct` | `NUMERIC` | Sí | Variación porcentual respecto del mes inmediatamente anterior. |
| `yoy_change_pct` | `NUMERIC` | Sí | Variación porcentual respecto del mismo mes del año anterior. |
| `source_run_id` | `UUID` | No | FK a `ops.runs.run_id`, ejecución del cálculo vigente. |
| `calculated_at` | `TIMESTAMPTZ` | No | Instante de cálculo. |

Las entradas conservadas deben coincidir con Silver y con el agregado FIX referenciado. Las variaciones son nulas si su comparador queda fuera del intervalo publicado y admiten signo negativo. El publicador compara los campos analíticos completos con el cálculo validado y actualiza solo filas modificadas, las filas sin cambios conservan `source_run_id` y `calculated_at`.

## 9. ops.watermarks

**Granularidad:** el intervalo publicado de un producto. **PK:** `pipeline_name`.

| Campo | Tipo | Admite NULL | Significado |
|---|---|---|---|
| `pipeline_name` | `TEXT` | No | Identificador estable: `grain_reference_mxn`. |
| `start_month` | `DATE` | No | Primer mes del intervalo histórico publicado. |
| `published_through_month` | `DATE` | No | Último mes continuo publicado hasta Gold. |
| `initial_run_id` | `UUID` | No | FK a `ops.runs.run_id`, histórico que inicializó el producto. |
| `last_run_id` | `UUID` | No | FK a `ops.runs.run_id`, última publicación confirmada. |
| `updated_at` | `TIMESTAMPTZ` | No | Instante de actualización del control. |

Los dos meses deben ser primeros de mes y estar ordenados. La fila se crea al cerrar una publicación histórica completa. El lector verifica el origen histórico exitoso y la última ejecución publicada, el finalizador comprueba Silver y Gold antes de cerrar el avance. Una revisión conserva los límites, una ampliación debe ser continua y `initial_run_id` se mantiene. Una revisión aprobada actualiza `last_run_id` aunque no cambien los hechos. El cierre de éxito y el watermark se confirman en la misma transacción que las capas. Un incremental `skipped` verifica el producto existente y conserva todos los campos de esta fila, incluido `last_run_id` y `updated_at`.

## 10. ops.schema_migrations

**Granularidad:** una versión SQL aplicada. **PK:** `version`. Tabla técnica de preparación, adicional a las ocho entidades del modelo.

| Campo | Tipo | Admite NULL | Significado |
|---|---|---|---|
| `version` | `TEXT` | No | Identificador del recurso aplicado: `001_initial`. |
| `checksum` | `TEXT` | No | SHA-256 del SQL con saltos de línea normalizados a LF. |
| `applied_at` | `TIMESTAMPTZ` | No | Instante de la transacción que aplicó la versión. |

El preparador confirma esta fila junto con las tablas y el catálogo. Una repetición comprueba la versión y el checksum, una diferencia detiene la operación. Las futuras modificaciones requerirán una nueva versión y su migración explícita. El SQL aplicado se conservará.
