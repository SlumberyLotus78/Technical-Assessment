# Catálogo de reglas de calidad y publicación

## 1. Alcance y estado

Este catálogo relaciona los controles de exploración con las validaciones del [modelo de datos](MODELO_DATOS_ES.md). El [perfilamiento inicial](Perfilamiento_inicial.md) acredita los resultados de la muestra. Los comandos histórico e incremental ejecutan y persisten controles sobre su ventana y sobre el producto completo antes de publicar.

La columna de implementación describe los controles disponibles en el código. Los estados `passed`, `failed` y `pending` describen el resultado de una evaluación, no el avance de desarrollo de una regla. Por ejemplo, el perfil de muestra deja pendiente la cobertura bancaria porque solo diagnostica filas, la regla mensual DQ-09 está implementada y exige un calendario revisado antes de publicar.

La persistencia del perfil genera códigos en `ops.dq_results.rule_code`, vinculados a captura e intento. Ambos coordinadores integran extracción y publicador, con controles por ventana y del conjunto completo. Las guías de [histórico](GUIA_CARGA_HISTORICA_ES.md), [incremental](GUIA_CARGA_INCREMENTAL_ES.md) y [publicación Gold](GUIA_PUBLICACION_GOLD_ES.md) documentan sus funciones y pruebas.

## 2. Fuentes y registros

| Código | Regla | Implementación actual | Condición requerida para cargar |
|---|---|---|---|
| `SRC-01` | Proveedor y serie conocidos, identidad coherente con la consulta. | Catálogo, `read_series_record`, `fetch_metadata` y `read_observations`, compartidos por diagnósticos y cargas. | Coincidencia de identificadores donde el proveedor los entrega, contexto de petición y metadatos validados. |
| `SRC-02` | Título, unidad, frecuencia, clasificación y disponibilidad compatibles. | Validación API y del registro archivado, publicación comprueba metadatos y fechas observadas frente a disponibilidad. | Contrato aprobado y rango interpretable. |
| `SRC-03` | Estructura de observaciones y respuesta completa para la ventana. | Contrato aplicado a cada ventana anual, después de archivar y registrar la respuesta, se repite antes de publicar. | Campos presentes y ausencia de error de fuente, controles FRED de página, unidades y tipo de salida compatibles. |
| `DQ-01` | Fechas válidas según el proveedor. | Perfil, preparación Silver y registro de evaluación implementados. | Cero fechas inválidas. |
| `DQ-02` | Fechas dentro de la ventana solicitada. | Perfil y escritura Silver, se exige además que la captura esté dentro del intervalo del intento. | Cero observaciones fuera de ventana. |
| `DQ-03` | Valores con formato numérico válido y finito. | Interpretación, preparación Silver y registro de evaluación implementados. | Cero formatos o tipos incompatibles. |
| `DQ-04` | Valores requeridos presentes. | Marcadores de `quality/values.py`, preparación Silver y registro de evaluación implementados. | Cero valores ausentes en las observaciones requeridas. |
| `DQ-05` | Precios y FIX positivos. | Perfil, preparación Silver y registro de evaluación implementados. | Cero valores menores o iguales a cero. |
| `DQ-06` | Fecha única dentro de cada serie y entrada procesada. | Implementada por captura, en Gold y al reunir los fragmentos registrados, el publicador conserva métricas globales. | Cero duplicados en todas las páginas y fragmentos de la carga. |
| `DQ-07` | Primer día como identificador de cada periodo mensual. | Contratos, preparación Silver y registro de evaluación implementados. | Cero identificadores mensuales incompatibles. |
| `DQ-08` | Meses esperados con valor utilizable. | Evaluada por captura y para los tres granos del intervalo reunido, con registro global antes de publicar. | Igualdad de los meses requeridos con los recibidos y validados, cero meses ausentes. |
| `DQ-09` | Cobertura FIX contra calendario bancario versionado. | Referencias 2009–2026, evaluación mensual en perfil histórico y SQL. Años sin referencia bloqueados antes de consultar observaciones. | Igualdad de conjuntos de fechas esperadas y válidas, sin duplicados ni valores ausentes. |

Un campo estructural ausente detiene el contrato. Un campo presente con valor incompatible queda contabilizado en el perfil. Para una carga, las incidencias sobre registros requeridos impiden publicar el intervalo afectado, no se eliminan filas ni se sustituyen valores para aparentar cobertura.

Las consultas se dividen en años calendario. Cada serie FRED mensual requiere como máximo doce periodos por ventana y su contrato exige una respuesta completa. Los perfiles consolidados y el publicador comprueban los límites de todos los fragmentos reunidos.

## 3. Procedencia, transformación y persistencia

| Código | Regla | Estado | Evidencia o condición exigida |
|---|---|---|---|
| `LIN-01` | Captura íntegra y vinculada a su serie y ejecución. | Hash, contexto y valores Silver contra sus originales comprobados antes de reutilizar el histórico o finalizar la publicación. | Archivo existente, SHA-256 coincidente y correspondencia entre observación, serie y captura de tipo `observations`. |
| `PUB-01` | Dependencias mensuales completas. | Publicador exige un intervalo entrante completo antes de combinarlo con Silver y registra su aprobación. | Por cada mes, tres precios de granos y un agregado FIX con todas sus reglas obligatorias aprobadas. |
| `PUB-02` | Cálculos y unidades coherentes. | Reconstrucción del intervalo completo y comparación de todos los campos Gold, antes del cierre. | Media FIX, conversión y variaciones reproducibles con la política decimal del modelo, entradas iguales a las fuentes validadas. |
| `PUB-03` | Claves, referencias y tipos compatibles con el diccionario. | Restricciones SQL y verificaciones del publicador integradas y probadas en PostgreSQL aislado. | PK, FK, campos obligatorios y restricciones de fila, además de las verificaciones de contexto del proceso. |
| `PUB-04` | Reejecución sin duplicaciones y tratamiento de revisiones. | Escritura condicionada al cambio en Silver y Gold, revisiones y variaciones dependientes verificadas. | Una fila vigente por clave, actualizaciones de valores revisados, conservación de procedencia previa y recálculo de Gold dependiente. |

Las restricciones SQL implementadas refuerzan campos obligatorios, claves y condiciones que dependen de una fila. Las funciones de carga aplican además las reglas de cobertura, identidad de la captura y consistencia entre entradas y resultados. Una FK o un conteo no sustituyen esas verificaciones. La [evidencia SQL inicial](evidencias/preparacion_postgres/validacion.json) y la [validación final](VALIDACION_FINAL_ES.md) identifican sus respectivas pruebas en bases aisladas.

Los precios, el FIX y las referencias deben ser finitos y positivos. Las variaciones porcentuales deben ser finitas cuando existen, admiten cero y valores negativos, y son nulas cuando el comparador queda fuera del histórico publicado.

## 4. Control de ejecución

| Código | Regla | Estado | Condición exigida |
|---|---|---|---|
| `CTL-01` | Histórico completo antes del primer incremental. | Coordinador incremental exige watermark válido antes de consultar APIs, publicador y cierre sin trabajo verifican el intervalo vigente. | Watermark creado por un histórico confirmado hasta Gold, con intervalo continuo publicado. |
| `CTL-02` | Meses cerrados y avance sustentado. | Plan incremental según las cuatro fuentes, corte opcional y revisión de cero a doce meses, validación completa del intervalo, sin huecos ni cambios del inicio histórico. | Corte compatible con fuentes y fecha de operación, avance solo por meses con todas las dependencias y controles aprobados. |
| `CTL-03` | Publicación atómica. | Commit conjunto y reversión verificados, incluso tras actualizar watermark y éxito. | Silver, Gold, watermark y estado `succeeded` se confirman juntos, ante fallo se conserva el último estado publicado. |
| `CTL-04` | Publicaciones serializadas y recuperación trazable. | Bloqueo de sesión, diagnóstico durable y cierre de fallos, recuperación explícita obtiene el mismo bloqueo antes de cerrar un huérfano. | Bloqueo del mismo producto y registro durable del intento, sus verificaciones y su eventual fallo. |
| `CTL-05` | Recuperación segura y reproceso identificado. | Módulos separados para decisión, límites y persistencia. Se registra operación, intento de origen e identificadores reutilizados. | Conjunto completo y sin publicación posterior para recuperar, intervalo ya publicado para reprocesar, intento nuevo y procedencia original preservada. |

Las dos modalidades invocan las mismas reglas y transformaciones mediante comandos independientes. La revisión incremental predeterminada comprende los últimos tres meses publicados y todos los meses nuevos. Una disponibilidad declarada anterior al avance existente bloquea la ejecución, los metadatos nunca sustituyen la comprobación de las observaciones.

Con revisión desactivada y sin meses seleccionados, el incremental se registra como `skipped` después de comprobar inicialización, disponibilidad del último mes y correspondencia de Silver/Gold con sus capturas. Conserva todos los campos del watermark y los hechos. Una revisión efectivamente ejecutada y aprobada se registra como `succeeded`, incluso con cero escrituras de hechos.

El dashboard aplica el contrato de `quality/analytics.py` antes de presentar el producto: tres granos por mes, FIX certificado y compartido, referencias conciliadas y variaciones por fecha exacta. Estas comprobaciones son de lectura, no crean ejecuciones ni cambian DQ de las cargas.

## 5. Tratamiento de resultados

Los resultados de las reglas son `passed`, `failed` o `pending`. Un resultado obligatorio `failed` o `pending` bloquea la publicación del alcance solicitado. La revisión de una captura o de un caso particular no cambia automáticamente un fallo por aprobación: es necesario corregir su causa, completar la evidencia o documentar y verificar una regla aplicable.

Los intentos conservan sus capturas y métricas para explicar el resultado. Los mensajes de error se construyen con identificadores públicos y datos operativos, sin incluir valores de credenciales. Las verificaciones se repiten al reprocesar datos revisados.

El perfil inicial conserva `DQ-09` pendiente como registro de esa exploración. La [comprobación mensual posterior](evidencias/calendario_gold/vista_previa.json) aprobó la muestra real de septiembre de 2026 en memoria. La [verificación del publicador](evidencias/publicacion_gold/validacion.json) comprobó después las transacciones con datos ficticios. Se confirmó la ejecución histórica real con los resultados esperados. La [evidencia incremental](evidencias/carga_incremental/validacion.json) registra la ampliación técnica de pruebas con HTTP simulado, cada ejecución real conserva sus propias capturas y controles.
