# Catálogo de reglas de calidad y publicación

## 1. Alcance y estado

Este catálogo relaciona los controles existentes de exploración con las validaciones requeridas para el [modelo de datos](MODELO_DATOS_ES.md). El [perfilamiento inicial](Perfilamiento_inicial.md) acredita los resultados de la muestra, la ejecución y persistencia de controles sobre el histórico completo se implementarán con las cargas.


Los códigos de este documento se usarán en `ops.dq_results.rule_code` al incorporar la persistencia de verificaciones. Las funciones actuales todavía no generan filas con esos identificadores.

## 2. Fuentes y registros

| Código | Regla | Implementación actual | Condición requerida para cargar |
|---|---|---|---|
| `SRC-01` | Proveedor y serie conocidos, identidad coherente con la consulta. | Catálogo, `read_series_record`, `fetch_metadata` y `read_observations`. Implementada en exploración. | Coincidencia de identificadores donde el proveedor los entrega. Contexto de petición y metadatos validados. |
| `SRC-02` | Título, unidad, frecuencia, clasificación y disponibilidad compatibles. | `validate_metadata` y `read_metadata_range`. Implementada en exploración. | Contrato aprobado y rango interpretable. |
| `SRC-03` | Estructura de observaciones y respuesta completa para la ventana. | `read_observations`. Implementada para la muestra de una página. | Campos presentes y ausencia de error de fuente. Controles FRED de página, unidades y tipo de salida compatibles. |
| `DQ-01` | Fechas válidas según el proveedor. | `parse_date` y `profile_observations`. Implementada en exploración. | Cero fechas inválidas. |
| `DQ-02` | Fechas dentro de la ventana solicitada. | `profile_observations`. Implementada en exploración. | Cero observaciones fuera de ventana. |
| `DQ-03` | Valores con formato numérico válido y finito. | `parse_source_value` y perfil. Implementada en exploración. | Cero formatos o tipos incompatibles. |
| `DQ-04` | Valores requeridos presentes. | Marcadores de `quality/values.py` y perfil. Implementada en exploración. | Cero valores ausentes en las observaciones requeridas. |
| `DQ-05` | Precios y FIX positivos. | `profile_observations`. Implementada en exploración. | Cero valores menores o iguales a cero. |
| `DQ-06` | Fecha única dentro de cada serie y entrada procesada. | Conteo de apariciones adicionales en el perfil. Implementada en exploración. | Cero duplicados.  Comparar páginas y fragmentos de toda la carga, no solo cada respuesta por separado. |
| `DQ-07` | Primer día como identificador de cada periodo mensual. | `profile_observations` y contrato de fechas mensuales. Implementada en exploración. | Cero identificadores mensuales incompatibles. |
| `DQ-08` | Meses esperados con valor utilizable. | `expected_months` y `missing_months` del perfil. Implementada en exploración. | Igualdad de los meses requeridos con los recibidos y validados, cero meses ausentes. |
| `DQ-09` | Cobertura FIX contra calendario bancario versionado. | Pendiente en el perfil actual informa `pending_banking_calendar`. | Igualdad de conjuntos de fechas esperadas y válidas, sin duplicados ni valores ausentes. |

Un campo estructural ausente detiene el contrato. Un campo presente con valor incompatible queda contabilizado en el perfil. Para una carga, las incidencias sobre registros requeridos impedirán publicar el intervalo afectado, no se eliminarán filas ni se sustituirán valores para aparentar cobertura.

Las consultas extensas deberán comprobarse en conjunto, incluidos límites de fragmentos y páginas. El control actual de una página FRED será una pieza reutilizable, no una evidencia de paginación histórica ya implementada.

## 3. Procedencia, transformación y persistencia

| Código | Regla | Estado | Evidencia o condición exigida |
|---|---|---|---|
| `LIN-01` | Captura íntegra y vinculada a su serie y ejecución. | Captura local implementada, registro SQL y comprobación operativa de hash pendientes. | Archivo existente, SHA-256 coincidente y correspondencia entre observación, serie y captura de tipo `observations`. |
| `PUB-01` | Dependencias mensuales completas. | Pendiente. | Por cada mes, tres precios de granos y un agregado FIX con todas sus reglas obligatorias aprobadas. |
| `PUB-02` | Cálculos y unidades coherentes. | Pendiente. | Media FIX, conversión y variaciones reproducibles con la política decimal del modelo, entradas iguales a las fuentes validadas. |
| `PUB-03` | Claves, referencias y tipos compatibles con el diccionario. | Pendiente de SQL y cargas. | PK, FK, campos obligatorios y restricciones de fila, además de las verificaciones de contexto del proceso. |
| `PUB-04` | Reejecución sin duplicaciones y tratamiento de revisiones. | Pendiente. | Una fila vigente por clave, actualizaciones de valores revisados, conservación de procedencia previa y recálculo de Gold dependiente. |

Las restricciones SQL reforzarán campos obligatorios, claves y condiciones que dependen de una fila. Las reglas de cobertura, identidad de la captura y consistencia entre entradas y resultados se aplicarán en funciones de carga. No se atribuirá a una FK o a un conteo una garantía que necesita esas verificaciones adicionales.

Los precios, el FIX y las referencias deberán ser finitos y positivos. Las variaciones porcentuales deberán ser finitas cuando existan, admiten cero y valores negativos, y serán nulas cuando el comparador quede fuera del histórico publicado.

## 4. Control de ejecución

| Código | Regla | Estado | Condición exigida |
|---|---|---|---|
| `CTL-01` | Histórico completo antes del primer incremental. | Pendiente. | Watermark creado por un histórico confirmado hasta Gold, con intervalo continuo publicado. |
| `CTL-02` | Meses cerrados y avance sustentado. | Selección de muestra implementada, publicación pendiente. | Corte compatible con fuentes y fecha de operación, avance solo por meses con todas las dependencias y controles aprobados. |
| `CTL-03` | Publicación atómica. | Pendiente. | Silver, Gold, watermark y estado `succeeded` se confirman juntos.  Ante fallo se conserva el último estado publicado. 
| `CTL-04` | Publicaciones serializadas y recuperación trazable. | Pendiente. | Bloqueo del mismo producto y registro durable del intento, sus verificaciones y su eventual fallo. |

Las dos modalidades de carga invocarán las mismas reglas y transformaciones. Cada una tendrá su propio comando y condiciones de inicio. Un incremental sin trabajo podrá registrarse como `skipped`, siempre que haya comprobado su inicialización, y conservará el watermark existente.

## 5. Tratamiento de resultados

Los resultados de las reglas serán `passed`, `failed` o `pending`. Un resultado obligatorio `failed` o `pending` bloqueará la publicación del alcance solicitado. La revisión de una captura o de un caso particular no cambiará automáticamente un fallo por aprobación: será necesario corregir su causa, completar la evidencia o documentar y verificar una regla aplicable.

Los intentos conservarán sus capturas y métricas para explicar el resultado. Los mensajes de error se construirán con identificadores públicos y datos operativos, sin incluir valores de credenciales. Las verificaciones se repetirán al reprocesar datos revisados.

La muestra inicial tiene cero incidencias en las reglas aplicadas, pero `DQ-09` continúa pendiente. Por esa razón sus 21 registros FIX son evidencia de exploración y aún no acreditan un agregado mensual publicable bajo este contrato.
