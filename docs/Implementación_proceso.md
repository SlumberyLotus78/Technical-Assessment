# Proceso de implementación

**Corte del documento:** 3 de noviembre de 2026 4:00 pm.

## 1. Objetivo y estado del proyecto

El proyecto integra precios internacionales de maíz, trigo y soya de FRED con el tipo de cambio FIX de Banxico para preparar referencias mensuales en pesos mexicanos. El alcance y las etapas previstas se mantienen en el [plan de implementación](../PLAN_IMPLEMENTACION_ES.md).

Se completó la preparación del entorno, la conexión autenticada a las fuentes, la validación de sus metadatos y la extracción de una muestra con conservación de respuestas y perfil de calidad. La muestra contiene 30 observaciones y completó las reglas de perfil sin incidencias. Una comprobación posterior del FIX de septiembre de 2026 validó sus 21 fechas contra el calendario bancario revisado.


Sobre esa evidencia se definieron el modelo, el diccionario y las reglas para las cargas. Se implementaron después las funciones de registro operativo, integridad de capturas, preparación y escritura Silver. Estas funciones se validaron en PostgreSQL aislado y la vista previa local preparó las 30 observaciones archivadas.

Se incorporaron las funciones compartidas de media FIX, referencias mensuales en MXN/t y variaciones por fecha exacta. La vista previa Gold produjo tres referencias para septiembre desde las capturas archivadas. Posteriormente se implementaron la persistencia Gold y el publicador transaccional, verificados con capturas ficticias en PostgreSQL aislado. Su conexión con la extracción histórica completa permanece pendiente.

Se incorporaron las funciones compartidas de media FIX, referencias mensuales en MXN/t y variaciones por fecha exacta. La vista previa Gold produjo tres referencias para septiembre desde las capturas archivadas. Posteriormente se implementaron la persistencia Gold y el publicador transaccional. El coordinador histórico conectó la extracción con esas funciones y recorrió el periodo elegido con HTTP simulado y PostgreSQL aislado. La ejecución histórica con las APIs reales de esta rama queda por realizar.

Este documento registra el avance de implementación y sus verificaciones. El detalle cuantitativo se presenta en el [perfilamiento inicial](Perfilamiento_inicial.md).

## 2. Avance registrado

| Etapa | Trabajo realizado | Referencia |
|---|---|---|
| Entorno | Registro de Python 3.12.4, entorno virtual y exclusión de archivos locales. | `acb8167f` |
| Alcance | Documentación del objetivo, las capas, las cargas independientes y la organización por responsabilidades. | `8354ab51` |
| Fuentes | Catálogo de los tres precios de granos y del FIX de determinación, con unidades y frecuencias esperadas. | `8580e339` |
| Configuración | Lectura de credenciales privadas, prioridad del entorno y comprobaciones con valores ficticios. | `64967801` |
| Comunicación | Cliente HTTP autenticado y consulta de metadatos de las cuatro series. | `36d4934b` |
| Contratos | Validación de estructura, identidad, título, unidad, frecuencia y clasificación de las fuentes. | `c19019c1` |
| Selección temporal | Interpretación de fechas, disponibilidad declarada y ventanas para un mes cerrado común. | `66385444` |
| Extracción y perfil | Consulta de observaciones, captura por ejecución y controles de fechas, valores, duplicados y cobertura mensual. | `de1fb9d2` |
| Evidencia inicial | Revisión de la muestra real, reproducción del perfil y conservación de las capturas que sustentan sus resultados. | `de1fb9d2` |
| Modelo y calidad | Diseño de ocho entidades, diccionario de campos y reglas de publicación para histórico e incremental independientes. | `7eac5daf` |
| Preparación PostgreSQL | SQL inicial, tabla técnica de versiones, conexión privada, catálogo y verificación de solo lectura. | `d26c777` |
| Documentación de ejecución | README en inglés con resumen, requisitos, preparación de PostgreSQL y comando, seguimiento del desarrollo conservado en esta bitácora. | `4d3ea3fb` |
| Persistencia y preparación Silver | Registro de intentos, capturas y DQ, verificación de integridad, conversión a tipos comunes y escritura por clave natural. | `a12de0e9` |
| Calendario y transformaciones Gold | Referencia bancaria 2026, regla DQ-09, dependencias mensuales, media FIX, referencias MXN/t y variaciones. | `2aaef90c` |
| Publicación transaccional | Escritura Gold, procedencia Silver, validación global, bloqueo del producto y confirmación conjunta de capas, watermark y éxito. | `f114c100` |
| Coordinación histórica | Periodo explícito, referencias 2009–2026, consultas anuales, reintentos, perfil consolidado y publicación hasta Gold. | Avance actual, pendiente de commit. |

## 3. Organización de la implementación

El código se distribuye por responsabilidad mediante funciones y paquetes, donde las reglas de calidad se mantienen separadas del transporte y de la coordinación de la extracción.

| Componente | Responsabilidad implementada |
|---|---|
| `common/` | Configuración privada, fechas, operaciones de calendario y política decimal compartida. |
| `clients/` | HTTP, autenticación, tiempos de espera, reintentos acotados y errores controlados. |
| `sources/` | Catálogo, contratos, consultas, selección de ventanas y referencias bancarias anuales. |
| `extraction/` | Conservación de capturas de muestra y de los fragmentos históricos. |
| `quality/` | Interpretación decimal, perfil, aceptación, cobertura, continuidad, procedencia y comparación de resultados. |
| `persistence/` | Conexión, esquema, catálogo, intentos, capturas, DQ, Silver, Gold y watermark. |
| `transformations/` | Preparación Silver, media FIX, referencias MXN/t, variaciones y vistas previas locales. |
| `orchestration/` | Histórico inicial, perfil consolidado, preparación, bloqueo, commits, rollback y cierre. |
| `tests/` | Casos sin servidor y SQL, capturas ficticias y ejecutor con integración explícita. |

El flujo implementado consulta los metadatos, determina las ventanas, solicita las observaciones, conserva el JSON recibido y aplica el contrato y las reglas de perfil. Los números se interpretan directamente desde texto con `Decimal`, manteniendo la precisión disponible en las fuentes.

El [modelo de datos](MODELO_DATOS_ES.md), el [diccionario](DICCIONARIO_DATOS_ES.md) y el [catálogo DQ](REGLAS_CALIDAD_ES.md) especifican las responsabilidades de persistencia y transformación. El preparador implementa ocho tablas del modelo y `ops.schema_migrations` como control técnico. Las garantías de carga y publicación siguen diferenciadas de la exploración y de la preparación del esquema.

## 4. Captura y trazabilidad

Cada diagnóstico crea una carpeta independiente en `data/bronze/samples/`. Una ejecución completa conserva cuatro registros de metadatos, cuatro respuestas de observaciones y un perfil consolidado. Las capturas incluyen proveedor, código de serie, instante UTC y ventana de consulta.

Las respuestas de observaciones se guardan antes de comprobar su contrato, si una consulta o una estructura fallan entonces las capturas previas permanecen y la ejecución no genera el perfil final. 

Los archivos existentes se preservan mediante creación exclusiva.

La ejecución inicial examinada es `20261103T215513253606Z_f3eb3f86a0734026aa8761a7d23324f7`, con fecha de referencia 2026-11-03 y mes final de muestra 2026-09. Sus nueve archivos se conservaron en [evidencias de perfilamiento inicial](evidencias/perfilamiento_inicial/manifest.json). El manifiesto identifica la ejecución, las verificaciones y las sumas SHA-256 de cada archivo.

Las capturas operativas permanecen excluidas de Git. La copia seleccionada para documentar el perfil inicial se conserva dentro de `docs/evidencias/` y acompaña al informe.

## 5. Verificaciones y resultados

| Tipo de verificación | Evidencia disponible |
|---|---|
| Pruebas sin servidor | 133 casos aprobados, incluidos los nuevos de reintentos, ventanas, disponibilidad, archivo de respuestas y perfil histórico. |
| Pruebas SQL | 53 casos aprobados en PostgreSQL 18.6 aislado, incluidos diez nuevos del coordinador histórico, cero omisiones en la verificación completa. |
| Consultas reales previas | Confirmación de acceso, contratos de metadatos, disponibilidad y propuesta de ventanas de las cuatro series. |
| Muestra real | 3 observaciones por grano de julio a septiembre de 2026 y 21 observaciones FIX de septiembre: 30 registros en total. |
| Reproducción del perfil | Los cuatro perfiles recalculados desde las capturas coinciden con `profile.json`. |
| Calidad observada | Cero ausentes, formatos inválidos, valores no positivos, fechas incompatibles, fechas fuera de ventana y duplicados. |
| Cobertura mensual | Tres meses esperados y tres meses con valores utilizables en cada grano. |
| Cobertura diaria | Septiembre de 2026, igualdad de las 21 fechas esperadas y recibidas, sin faltantes, inesperadas o duplicadas. |
| Preparación Silver real | Las 30 observaciones archivadas se prepararon como `date` y `Decimal` sin consultar APIs ni escribir en la base del proyecto. |
| Transformación Gold real | 24 entradas del mes seleccionado: tres precios y 21 FIX. Se produjeron una media y tres referencias MXN/t en memoria. |
| Publicación SQL con datos ficticios | Inicialización, repetición, revisiones, ampliación continua, visibilidad entre sesiones y reversión conjunta de capas y control. |
| Histórico técnico completo | Enero de 2009 a septiembre de 2026 con HTTP simulado: 76 capturas, 5,102 observaciones Silver, 213 agregados FIX y 639 referencias Gold. |


Las pruebas simuladas verifican el comportamiento del código mientras que la muestra real aporta evidencia sobre los registros efectivamente recibidos. Ambas verificaciones tienen alcances distintos y se documentan por separado.

El [resumen original de preparación PostgreSQL](evidencias/preparacion_postgres/validacion.json) registra 83 pruebas aprobadas, sin fallos ni omisiones, con Python 3.12.4 y Psycopg 3.3.7. Cada prueba SQL utilizó una base desechable propia dentro de una instancia temporal local, que se detuvo al terminar. La base indicada en el `.env` del proyecto no se utilizó para esas pruebas. En ese avance, sin conexión explícita de prueba se omitían los 11 casos SQL.

La ampliación posterior está sustentada por [108 pruebas aprobadas](evidencias/persistencia_silver/validacion.json) y una [vista previa normalizada](evidencias/persistencia_silver/vista_previa.json). De ellas, 22 utilizaron PostgreSQL aislado, la instancia temporal se cerró. Se comprobaron inserción, repetición sin cambios, revisión de una fila, preservación de procedencia, detección de archivos alterados y rollback decidido por el coordinador. Sin conexión de prueba, la suite ampliada omite esos 22 casos.

### 5.1. Ejecución de la validación y generación de evidencias

Se preparó una instancia PostgreSQL temporal. El clúster se ubicó en `data/verification/`, escuchó en `127.0.0.1` con un puerto separado del servicio del proyecto y utilizó una cuenta de prueba. Cada caso SQL creó y eliminó su propia base `grain_test_<uuid>`, con datos ficticios para comprobar las operaciones y restricciones.

Desde PowerShell se ejecutaron scripts auxiliares de Python que establecieron `TEST_DATABASE_URL` hacia esa instancia antes de cargar las pruebas. La selección se realizó con `unittest.defaultTestLoader.discover("tests")` y la ejecución con `unittest.TextTestRunner`. Se obtuvieron del resultado los casos ejecutados, fallos, errores, omisiones y aprobación global, se añadieron las versiones del entorno, la fecha UTC y el checksum del SQL calculado por `schema_resource()`.

Los resultados se serializaron como JSON. La comprobación del preparador produjo `preparacion_postgres/validacion.json` con 83 pruebas aprobadas, la ampliación de persistencia produjo `persistencia_silver/validacion.json` con 108. Corresponden a dos verificaciones realizadas en momentos distintos del desarrollo. Los resúmenes conservados están vinculados en esta sección y documentan sus respectivos entornos y alcances.

Para generar `persistencia_silver/vista_previa.json` se procesaron las cuatro capturas reales de observaciones conservadas en `docs/evidencias/perfilamiento_inicial/`. Los scripts invocaron `read_capture`, `get_series`, `read_observations` y `prepare_observations`, comprobaron los hashes contra el manifiesto y verificaron que las fechas fueran objetos `date` y los valores fueran `Decimal`. Se prepararon 30 observaciones y se conservaron sus referencias de origen. Al exportar el JSON, las fechas se expresaron mediante `isoformat()` y los decimales mediante `str()`, manteniendo sus dígitos.

También se ejecutó el comando `python -X utf8 -m grain_pipeline.transformations.silver` para comprobar la vista previa en terminal. La normalización de las capturas archivadas se realizó en memoria, sin consultas nuevas a las APIs ni escritura de esos registros en la base del proyecto. La cobertura bancaria FIX permaneció identificada como pendiente.

Al terminar las pruebas se cerró la instancia temporal. Los informes documentales se exportaron mediante scripts ejecutados en línea durante la sesión de PowerShell, esos generadores no quedaron incorporados como archivos `.py` reutilizables. Las pruebas y funciones invocadas forman parte del código del proyecto. Los archivos de `docs/evidencias/` son registros de esas ejecuciones y no una exportación automática de los comandos de preparación o vista previa.

### 5.2. Referencia bancaria y verificación de las transformaciones Gold

Se revisó la definición de FIX de determinación de Banxico y la publicación de las disposiciones de cierre bancario 2026 de la CNBV en el DOF. Se cotejaron las fechas con la relación de la Asociación de Bancos de México. Las fuentes, fechas de publicación y revisión, fines de semana y cierres quedaron registrados en `sources/calendars/2026.json`. La referencia se identificó mediante versión y SHA-256 con saltos de línea normalizados.

Se separó la lectura del calendario de la regla `DQ-09`. Esta última comparó las fechas FIX utilizables con las esperadas y conservó los faltantes, inesperados, duplicados y registros inválidos. Los años sin referencia revisada quedaron como `pending`, condición que impide generar el agregado. La regla se probó también con 21 filas cuyo conteo coincide, pero cuyas fechas no corresponden al calendario: la evaluación falló como se requería.

Se implementaron funciones independientes para validar el conjunto Silver, agregar FIX y construir Gold. Se exigieron meses cerrados, claves únicas y los tres precios por mes. Los cálculos utilizaron contextos decimales locales de 34 dígitos y `ROUND_HALF_EVEN`. Las variaciones se asociaron al mes anterior y al mismo mes del año previo, una ausencia interior bloqueó el cálculo. Una revisión ficticia de agosto comprobó el recálculo de su referencia y de la variación dependiente de septiembre.

La suite completa se ejecutó con Python 3.12.4 mediante un script Python en línea desde PowerShell, con `unittest.TestLoader().discover("tests")` y `unittest.TextTestRunner`. Para esta ejecución se retiró `TEST_DATABASE_URL` únicamente del entorno del proceso de prueba. Se descubrieron 130 casos, se ejecutaron 108 sin fallos ni errores y se omitieron los 22 que requieren PostgreSQL. Los contadores y el contexto de ejecución se exportaron a [validacion.json](evidencias/calendario_gold/validacion.json). No se inició una instancia ni se repitieron las pruebas SQL del avance Silver.

La vista previa real se ejecutó mediante el comando incorporado al proyecto:

```powershell
python -X utf8 -m grain_pipeline.transformations.gold_preview --month 2026-09 --sample-dir docs/evidencias/perfilamiento_inicial --bronze-root docs/evidencias/perfilamiento_inicial --output docs/evidencias/calendario_gold/vista_previa.json
```

La carpeta de destino se creó previamente. El comando validó las cuatro capturas completas, preparó Silver y seleccionó 24 entradas de septiembre. Certificó las 21 fechas FIX y obtuvo una media de `17.26401904761904761904761904761905` MXN/USD. Las referencias resultantes fueron aproximadamente 4,090.12 MXN/t para maíz, 4,261.65 para trigo y 8,316.46 para soya. MoM y YoY quedaron nulos al no incluir comparadores en esta vista previa de un mes.

El [informe Gold](evidencias/calendario_gold/vista_previa.json) conservó valores completos, hashes de origen y métricas de calendario. Su exportación quedó disponible con `--output` en el módulo `gold_preview.py`, que rechaza sobrescribir archivos existentes. No se consultaron APIs, no se escribieron observaciones en PostgreSQL y no se modificaron watermarks. Las capturas, el perfil y las evidencias anteriores permanecieron intactos.

### 5.3. Persistencia Gold y verificación de la publicación atómica

Se añadieron módulos separados para las reglas del intervalo publicado, la escritura Gold, la lectura del watermark y el bloqueo del producto. Se incorporó `orchestration/` para coordinar la preparación y las transacciones mediante funciones. El recurso SQL inicial permaneció sin modificaciones y no se requirieron dependencias nuevas.

Se revalidaron los metadatos desde sus registros Bronze y se reunieron las observaciones de las cuatro series. Se registraron controles por captura y de conjunto, incluidos duplicados entre fragmentos, meses de granos faltantes y cobertura FIX mensual. El conjunto recibido debió estar completo por sí mismo antes de combinarse con Silver vigente. También se comprobó que cada fila Silver coincidiera con su captura íntegra de la misma serie y fecha.

La preparación confirmó sus resultados DQ antes de modificar las capas. Una segunda transacción actualizó Silver, reconstruyó Gold para el intervalo publicado y confirmó watermark y estado exitoso juntos. Las escrituras Gold conservaron la auditoría de filas sin cambios. Un bloqueo de sesión mantuvo la exclusión entre esas transacciones. Los fallos de publicación revirtieron sus escrituras y se registraron después con etapa y resumen controlado.

Se construyó un ejecutor reutilizable en `tests/run.py`. Con `--postgres` leyó la conexión de prueba antes del descubrimiento, validó su prefijo y exigió cero omisiones. La clave de producción no se utilizó como alternativa. El parámetro `--report` permitió exportar contadores reales y los identificadores de los casos SQL ejecutados sin sobrescribir informes existentes.

Primero se ejecutaron 18 pruebas SQL nuevas en la instancia temporal y finalizaron correctamente. Después de completar las comprobaciones de visibilidad, duplicados globales y protección del finalizador, se ejecutó la suite completa mediante `tests.run` con `--postgres --report`. La conexión se proporcionó en el entorno del proceso hacia el clúster local aislado, sin leer el `.env` real.

El resultado fue de **161 pruebas aprobadas: 118 sin servidor y 43 SQL**, con cero fallos, errores u omisiones, en Python 3.12.4 y PostgreSQL 18.6. Cada caso SQL utilizó una base desechable y capturas ficticias. Una segunda conexión confirmó que el estado anterior permanecía visible hasta el commit. Se inyectaron errores después de escribir Gold y después de actualizar watermark y éxito, todas esas modificaciones se revirtieron juntas. La revisión ficticia de agosto también actualizó la variación dependiente de septiembre.


### 5.4. Coordinador histórico y periodo seleccionado

Se incorporaron diecisiete referencias anuales adicionales a partir de la tabla curada del proyecto original, cuya revisión estaba registrada el 2026-11-02. Se conservaron la fecha de revisión, el commit de procedencia, la copia pública de la tabla y sus hashes. Se cotejaron los registros de publicación disponibles en SIDOF y se preservaron los cierres extraordinarios documentados de 2010 y 2024. El recurso 2026 previo permaneció intacto. El [manifiesto histórico](evidencias/calendario_historico/manifest.json) registró 213 meses y 4,463 fechas FIX esperadas, sin presentarlas como observaciones nuevamente consultadas.

Se separaron las ventanas anuales, las reglas de disponibilidad, las funciones de captura y el perfil consolidado. El coordinador adquirió el bloqueo del producto desde la planificación, registró el intento y confirmó cada captura antes de aplicar sus contratos. Se exigió una base sin watermark para la inicialización histórica. Las peticiones HTTP se realizaron con la conexión SQL sin transacción abierta, esta condición se comprobó durante la integración.

El cliente HTTP incorporó hasta tres intentos para fallos transitorios, con esperas acotadas y tratamiento de `Retry-After`. Las respuestas se cerraron antes de esperar. Los contratos y errores permanentes siguieron siendo bloqueantes. Las pruebas separaron el comportamiento de un único intento de los escenarios de recuperación y agotamiento.

La integración de PostgreSQL recorrió primero diez casos nuevos con HTTP simulado y terminó correctamente. Después se ejecutó la suite completa mediante `tests.run --postgres --report`, usando la conexión del clúster temporal en el entorno del proceso. El resultado fue de **186 pruebas aprobadas: 133 sin servidor y 53 SQL**, sin fallos, errores ni omisiones. El [informe de carga histórica](evidencias/carga_historica/validacion.json) conserva el resultado y distingue los datos ficticios utilizados.

El caso del intervalo completo realizó 76 llamadas HTTP simuladas y publicó 639 precios ficticios de 100 USD/t y 4,463 FIX ficticios de 20 MXN/USD. Se comprobaron 213 agregados, 639 referencias y 603 variaciones YoY con comparador. Otros casos verificaron fallos de red, metadatos incompatibles, respuestas parciales, cobertura incompleta y rechazo de una segunda inicialización. El comando de terminal también se probó con configuración ficticia y una base desechable.

### 5.5. Coordinador incremental y revisión de publicaciones

Se implementó un comando independiente que exige el watermark histórico antes de consultar las APIs. La planificación combina la disponibilidad de las cuatro series con el último mes cerrado en la zona de operación. La revisión predeterminada comprende los últimos tres meses publicados y todos los meses nuevos, se permite configurarla entre cero y doce y establecer un corte mensual opcional. Una regresión de disponibilidad, la falta de calendario revisado o una cobertura insuficiente bloquean la publicación.

Se trasladaron las funciones de captura a `extraction/captures.py` y las reglas temporales compartidas a `quality/windows.py`. Se separaron las consultas y registros, los artefactos y el cierre de fallos en módulos de orquestación reutilizables. El histórico conservó su interfaz y sus archivos. El incremental no invoca ese coordinador ni inicializa el producto de manera implícita. No se añadieron clases de aplicación, requisitos de instalación ni cambios en el SQL inicial.

La extracción quedó limitada a la ventana seleccionada. El publicador reutiliza Silver validado para reconstruir Gold sobre todo el intervalo y mantener comparadores MoM y YoY exactos. Se actualizan únicamente los valores que cambian. Con revisión desactivada y sin meses seleccionados se comprueban las capturas, Silver y Gold vigentes antes de registrar `skipped`, el watermark y las tablas de hechos permanecen iguales. Una revisión ejecutada puede cerrar `succeeded` con cero escrituras.

La verificación comenzó con los casos específicos de planificación y de ambos coordinadores. Después se ejecutó `tests.run --postgres --report` con la conexión del clúster temporal en el entorno del proceso y una ruta de configuración que no corresponde al `.env` real. La suite completa terminó con **209 pruebas aprobadas: 141 sin servidor y 68 SQL**, sin fallos, errores ni omisiones. El [informe incremental](evidencias/carga_incremental/validacion.json) registra los casos SQL y el alcance de la comprobación.

Las pruebas comprobaron revisiones de granos y FIX, recálculo de variaciones dependientes, recuperación continua de varios meses, cambio de año, cierre sin trabajo, integridad de la publicación previa y reversión después de modificar watermark y éxito. Un caso partió del histórico ficticio 2009-01 a 2026-09 y agregó octubre mediante ocho consultas lógicas, terminando con 5,127 observaciones Silver, 214 medias FIX y 642 referencias Gold. Los datos de esas APIs simuladas fueron valores ficticios, no constituyen una carga real adicional.

El clúster aislado se detuvo al terminar. No se leyó el `.env` real ni se escribió en la base del proyecto. Se actualizó el README en inglés, la documentación del modelo y las guías de ejecución.

## 6. Estado de las capas y cargas

| Frente | Estado al corte |
|---|---|
| Bronze | Muestras reales conservadas y captura histórica por ventanas implementada. |
| Silver | Integrada con el coordinador histórico y verificada en el intervalo completo con datos ficticios. |
| Gold | Transformaciones, escritura y publicación implementadas, muestra real calculada en memoria y publicación probada con datos ficticios. |
| Carga histórica | Comando inicial independiente, periodo elegido y calendarios incorporados. Recorrido hasta Gold probado, ejecución real de esta rama pendiente. |
| Carga incremental | Requisito de histórico y ampliación continua probados en el publicador. Comando y planificación independientes pendientes. |
| Persistencia y control | Publicador sobre capturas registradas, bloqueo de sesión, diagnóstico durable y watermark implementados y verificados. Recuperación automática pendiente. |
| Visualización y automatización | Pendientes del modelo analítico, el paquete instalable y la programación del incremental. |


La extracción de muestra es un diagnóstico de fuentes. El histórico inicial invoca el publicador para confirmar el periodo completo la ejecución real generará sus propias capturas, métricas y estado durable.

## 7. Continuidad prevista

El siguiente desarrollo incorporará el incremental independiente sobre el watermark histórico, con una ventana de revisión definida.

La carga histórica establecerá la base inicial hasta Gold y las cargas incrementales se implementará después como proceso independiente, compartiendo reglas y transformaciones, con control de reejecuciones y actualización de watermarks tras una publicación satisfactoria. La visualización y el empaquetado para automatización se incorporarán sobre esa base.

Esta bitácora se actualizará con cada avance, su referencia de commit, la evidencia obtenida y los pendientes que afecten a las etapas posteriores.
