# Catálogo de reglas de calidad y publicación

## 1. Alcance y estado

Este catálogo relaciona los controles existentes de exploración con las validaciones requeridas para el [modelo de datos](MODELO_DATOS_ES.md). El [perfilamiento inicial](Perfilamiento_inicial.md) acredita los resultados de la muestra, la ejecución y persistencia de controles sobre el histórico completo se implementarán con las cargas.

«Implementada en exploración» significa que existe una función de contrato o perfil, verificada con escenarios simulados y aplicada a la muestra real. No acredita todavía integración con PostgreSQL. «Pendiente» identifica un control cuyo mecanismo de carga o publicación falta construir.

La persistencia del perfil genera códigos en `ops.dq_results.rule_code`, vinculados a captura e intento. El histórico inicial integra extracción y publicador, con controles por ventana y del conjunto completo.


## 2. Fuentes y registros

| Código | Regla | Implementación actual | Condición requerida para cargar |
|---|---|---|---|
| `SRC-01` | Proveedor y serie conocidos, identidad coherente con la consulta. | Catálogo, `read_series_record`, `fetch_metadata` y `read_observations`. Implementada en exploración. | Coincidencia de identificadores donde el proveedor los entrega. Contexto de petición y metadatos validados. |
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

Un campo estructural ausente detiene el contrato. Un campo presente con valor incompatible queda contabilizado en el perfil. Para una carga, las incidencias sobre registros requeridos impedirán publicar el intervalo afectado, no se eliminarán filas ni se sustituirán valores para aparentar cobertura.

Las consultas se dividen en años calendario. Cada serie FRED mensual requiere como máximo doce periodos por ventana y su contrato exige una respuesta completa. Los perfiles consolidados y el publicador comprueban los límites de todos los fragmentos reunidos.

## 3. Procedencia, transformación y persistencia

| Código | Regla | Estado | Evidencia o condición exigida |
|---|---|---|---|
| `LIN-01` | Captura íntegra y vinculada a su serie y ejecución. | Hash, contexto y valores Silver contra sus originales comprobados antes de reutilizar el histórico o finalizar la publicación. | Archivo existente, SHA-256 coincidente y correspondencia entre observación, serie y captura de tipo `observations`. |
| `PUB-01` | Dependencias mensuales completas. | Publicador exige un intervalo entrante completo antes de combinarlo con Silver y registra su aprobación. | Por cada mes, tres precios de granos y un agregado FIX con todas sus reglas obligatorias aprobadas. |
| `PUB-02` | Cálculos y unidades coherentes. | Reconstrucción del intervalo completo y comparación de todos los campos Gold, antes del cierre. | Media FIX, conversión y variaciones reproducibles con la política decimal del modelo, entradas iguales a las fuentes validadas. |
| `PUB-03` | Claves, referencias y tipos compatibles con el diccionario. | Restricciones SQL y verificaciones del publicador integradas y probadas en PostgreSQL aislado. | PK, FK, campos obligatorios y restricciones de fila, además de las verificaciones de contexto del proceso. |
| `PUB-04` | Reejecución sin duplicaciones y tratamiento de revisiones. | Escritura condicionada al cambio en Silver y Gold, revisiones y variaciones dependientes verificadas. | Una fila vigente por clave, actualizaciones de valores revisados, conservación de procedencia previa y recálculo de Gold dependiente. |

Las restricciones SQL implementadas refuerzan campos obligatorios, claves y condiciones que dependen de una fila. Las reglas de cobertura, identidad de la captura y consistencia entre entradas y resultados se aplicarán en funciones de carga. No se atribuirá a una FK o a un conteo una garantía que necesita esas verificaciones adicionales. La [evidencia SQL](evidencias/preparacion_postgres/validacion.json) corresponde a bases de prueba aisladas.

Los precios, el FIX y las referencias deberán ser finitos y positivos. Las variaciones porcentuales deberán ser finitas cuando existan, admiten cero y valores negativos, y serán nulas cuando el comparador quede fuera del histórico publicado.

## 4. Control de ejecución

| Código | Regla | Estado | Condición exigida |
|---|---|---|---|
| `CTL-01` | Histórico completo antes del primer incremental. | Publicador exige watermark originado por histórico exitoso y verifica el intervalo vigente, comando incremental pendiente. | Watermark creado por un histórico confirmado hasta Gold, con intervalo continuo publicado. |
| `CTL-02` | Meses cerrados y avance sustentado. | Plan de publicación y comprobaciones completas del intervalo implementados,rechaza huecos y cambios del inicio histórico. | Corte compatible con fuentes y fecha de operación, avance solo por meses con todas las dependencias y controles aprobados. |
| `CTL-03` | Publicación atómica. | Commit conjunto y reversión verificados, incluso tras actualizar watermark y éxito. | Silver, Gold, watermark y estado `succeeded` se confirman juntos, ante fallo se conserva el último estado publicado. |
| `CTL-04` | Publicaciones serializadas y recuperación trazable. | Bloqueo de sesión, diagnóstico durable y cierre de fallos implementados. Recuperación automática de interrupciones pendiente. | Bloqueo del mismo producto y registro durable del intento, sus verificaciones y su eventual fallo. |

Las dos modalidades de carga invocarán las mismas reglas y transformaciones. Cada una tendrá su propio comando y condiciones de inicio. Un incremental sin trabajo podrá registrarse como `skipped`, siempre que haya comprobado su inicialización, y conservará el watermark existente.

## 5. Tratamiento de resultados

Los resultados de las reglas serán `passed`, `failed` o `pending`. Un resultado obligatorio `failed` o `pending` bloqueará la publicación del alcance solicitado. La revisión de una captura o de un caso particular no cambiará automáticamente un fallo por aprobación: será necesario corregir su causa, completar la evidencia o documentar y verificar una regla aplicable.

Los intentos conservarán sus capturas y métricas para explicar el resultado. Los mensajes de error se construirán con identificadores públicos y datos operativos, sin incluir valores de credenciales. Las verificaciones se repetirán al reprocesar datos revisados.

El perfil inicial conserva `DQ-09` pendiente como registro de esa exploración. La [comprobación mensual posterior](evidencias/calendario_gold/vista_previa.json) aprobó la muestra real de septiembre de 2026 en memoria. La [verificación del publicador](evidencias/publicacion_gold/validacion.json) comprobó después las transacciones con datos ficticios. La ejecución histórica real deberá reunir sus propias capturas y recorrer estos controles antes de publicar su intervalo.