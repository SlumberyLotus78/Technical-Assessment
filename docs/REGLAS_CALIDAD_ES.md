# Catálogo de reglas de calidad y publicación

## 1. Alcance y estado

Este catálogo relaciona los controles existentes de exploración con las validaciones requeridas para el [modelo de datos](MODELO_DATOS_ES.md). El [perfilamiento inicial](Perfilamiento_inicial.md) acredita los resultados de la muestra, la ejecución y persistencia de controles sobre el histórico completo se implementarán con las cargas.

«Implementada en exploración» significa que existe una función de contrato o perfil, verificada con escenarios simulados y aplicada a la muestra real. No acredita todavía integración con PostgreSQL. «Pendiente» identifica un control cuyo mecanismo de carga o publicación falta construir.

La persistencia del perfil ya genera códigos de este catálogo en `ops.dq_results.rule_code`, vinculados a la captura y al intento. Los controles de publicación del producto completo se incorporarán con el coordinador de cargas.

## 2. Fuentes y registros

| Código | Regla | Implementación actual | Condición requerida para cargar |
|---|---|---|---|
| `SRC-01` | Proveedor y serie conocidos, identidad coherente con la consulta. | Catálogo, `read_series_record`, `fetch_metadata` y `read_observations`. Implementada en exploración. | Coincidencia de identificadores donde el proveedor los entrega. Contexto de petición y metadatos validados. |
| `SRC-02` | Título, unidad, frecuencia, clasificación y disponibilidad compatibles. | `validate_metadata` y `read_metadata_range`. Implementada en exploración. | Contrato aprobado y rango interpretable. |
| `SRC-03` | Estructura de observaciones y respuesta completa para la ventana. | `read_observations`. Implementada para la muestra de una página. | Campos presentes y ausencia de error de fuente. Controles FRED de página, unidades y tipo de salida compatibles. |
| `DQ-01` | Fechas válidas según el proveedor. | Perfil, preparación Silver y registro de evaluación implementados. | Cero fechas inválidas. |
| `DQ-02` | Fechas dentro de la ventana solicitada. | Perfil y escritura Silver, se exige además que la captura esté dentro del intervalo del intento. | Cero observaciones fuera de ventana. |
| `DQ-03` | Valores con formato numérico válido y finito. | Interpretación, preparación Silver y registro de evaluación implementados. | Cero formatos o tipos incompatibles. |
| `DQ-04` | Valores requeridos presentes. | Marcadores de `quality/values.py`, preparación Silver y registro de evaluación implementados. | Cero valores ausentes en las observaciones requeridas. |
| `DQ-05` | Precios y FIX positivos. | Perfil, preparación Silver y registro de evaluación implementados. | Cero valores menores o iguales a cero. |
| `DQ-06` | Fecha única dentro de cada serie y entrada procesada. | Implementada por captura y en el conjunto Silver recibido por Gold, reunión de fragmentos pendiente del coordinador. | Cero duplicados en todas las páginas y fragmentos de la carga. |
| `DQ-07` | Primer día como identificador de cada periodo mensual. | Contratos, preparación Silver y registro de evaluación implementados. | Cero identificadores mensuales incompatibles. |
| `DQ-08` | Meses esperados con valor utilizable. | Implementada por captura y para los tres granos de cada mes del intervalo recibido por Gold, integración con cargas pendiente. | Igualdad de los meses requeridos con los recibidos y validados, cero meses ausentes. |
| `DQ-09` | Cobertura FIX contra calendario bancario versionado. | `quality/calendar.py` compara las fechas antes del agregado, referencia 2026 incorporada. El perfil por captura mantiene `pending`, el resultado mensual se evalúa aparte. | Igualdad de conjuntos de fechas esperadas y válidas, sin duplicados ni valores ausentes, años sin referencia revisada bloqueados. |

Un campo estructural ausente detiene el contrato. Un campo presente con valor incompatible queda contabilizado en el perfil. Para una carga, las incidencias sobre registros requeridos impedirán publicar el intervalo afectado, no se eliminarán filas ni se sustituirán valores para aparentar cobertura.

Las consultas extensas deberán comprobarse en conjunto, incluidos límites de fragmentos y páginas. El control actual de una página FRED será una pieza reutilizable, no una evidencia de paginación histórica ya implementada.

## 3. Procedencia, transformación y persistencia

| Código | Regla | Estado | Evidencia o condición exigida |
|---|---|---|---|
| `LIN-01` | Captura íntegra y vinculada a su serie y ejecución. | Registro SQL y comprobación de hash y contexto implementados, verificados en PostgreSQL aislado. | Archivo existente, SHA-256 coincidente y correspondencia entre observación, serie y captura de tipo `observations`. |
| `PUB-01` | Dependencias mensuales completas. | Funciones Gold exigen tres precios y FIX certificado para todos los meses, evaluación y registro del publicador pendientes. | Por cada mes, tres precios de granos y un agregado FIX con todas sus reglas obligatorias aprobadas. |
| `PUB-02` | Cálculos y unidades coherentes. | Media, conversión y variaciones implementadas y probadas, verificación y registro en publicación pendientes. | Media FIX, conversión y variaciones reproducibles con la política decimal del modelo, entradas iguales a las fuentes validadas. |
| `PUB-03` | Claves, referencias y tipos compatibles con el diccionario. | Restricciones SQL implementadas y verificadas en PostgreSQL aislado, integración con cargas pendiente. | PK, FK, campos obligatorios y restricciones de fila, además de las verificaciones de contexto del proceso. |
| `PUB-04` | Reejecución sin duplicaciones y tratamiento de revisiones. | Repetición y revisiones Silver implementadas, recálculo Gold de intervalos probado. Escritura y coordinación de revisiones Gold pendientes. | Una fila vigente por clave, actualizaciones de valores revisados, conservación de procedencia previa y recálculo de Gold dependiente. |

Las restricciones SQL implementadas refuerzan campos obligatorios, claves y condiciones que dependen de una fila. Las reglas de cobertura, identidad de la captura y consistencia entre entradas y resultados se aplicarán en funciones de carga. No se atribuirá a una FK o a un conteo una garantía que necesita esas verificaciones adicionales. La [evidencia SQL](evidencias/preparacion_postgres/validacion.json) corresponde a bases de prueba aisladas.

Los precios, el FIX y las referencias deberán ser finitos y positivos. Las variaciones porcentuales deberán ser finitas cuando existan, admiten cero y valores negativos, y serán nulas cuando el comparador quede fuera del histórico publicado.

## 4. Control de ejecución

| Código | Regla | Estado | Condición exigida |
|---|---|---|---|
| `CTL-01` | Histórico completo antes del primer incremental. | Pendiente. | Watermark creado por un histórico confirmado hasta Gold, con intervalo continuo publicado. |
| `CTL-02` | Meses cerrados y avance sustentado. | Selección de muestra y rechazo de meses abiertos en Gold implementados, publicación pendiente. | Corte compatible con fuentes y fecha de operación, avance solo por meses con todas las dependencias y controles aprobados. |
| `CTL-03` | Publicación atómica. | Preparación SQL y control externo del commit Silver verificados; publicador completo pendiente. | Silver, Gold, watermark y estado `succeeded` se confirman juntos, ante fallo se conserva el último estado publicado. |
| `CTL-04` | Publicaciones serializadas y recuperación trazable. | Bloqueos de preparación y de fila de intento implementados, bloqueo del producto y recuperación de cargas pendientes. | Bloqueo del mismo producto y registro durable del intento, sus verificaciones y su eventual fallo. |

Las dos modalidades de carga invocarán las mismas reglas y transformaciones. Cada una tendrá su propio comando y condiciones de inicio. Un incremental sin trabajo podrá registrarse como `skipped`, siempre que haya comprobado su inicialización, y conservará el watermark existente.

## 5. Tratamiento de resultados

Los resultados de las reglas serán `passed`, `failed` o `pending`. Un resultado obligatorio `failed` o `pending` bloqueará la publicación del alcance solicitado. La revisión de una captura o de un caso particular no cambiará automáticamente un fallo por aprobación: será necesario corregir su causa, completar la evidencia o documentar y verificar una regla aplicable.

Los intentos conservarán sus capturas y métricas para explicar el resultado. Los mensajes de error se construirán con identificadores públicos y datos operativos, sin incluir valores de credenciales. Las verificaciones se repetirán al reprocesar datos revisados.

El perfil inicial conserva `DQ-09` pendiente como registro de esa exploración. La [comprobación mensual posterior](evidencias/calendario_gold/vista_previa.json) aprobó la cobertura FIX de septiembre de 2026 y produjo un agregado y tres referencias en memoria. La publicación del producto requiere todavía la integración transaccional, el registro operativo completo y las reglas del coordinador. 
