# Proceso de implementación

**Corte del documento:** 4 de noviembre de 2026.

**Ámbito:** repositorio `Technical-Assessment`, rama `main`.

## 1. Objetivo y estado del proyecto

El proyecto integra precios internacionales de maíz, trigo y soya de FRED con el tipo de cambio FIX de Banxico para preparar referencias mensuales en pesos mexicanos. El alcance y las etapas previstas se mantienen en el [plan de implementación](../PLAN_IMPLEMENTACION_ES.md).

Se completó la preparación del entorno, la conexión autenticada a las fuentes, la validación de sus metadatos y la extracción de una muestra con conservación de respuestas y perfil de calidad. La muestra contiene 30 observaciones y completó las reglas de perfil sin incidencias. Una comprobación posterior del FIX de septiembre de 2026 validó sus 21 fechas contra el calendario bancario revisado.

Sobre esa evidencia se definieron el modelo, el diccionario y las reglas para las cargas. Se confirmó la preparación del esquema y su comprobación de solo lectura en la base del proyecto. Se implementaron después las funciones de registro operativo, integridad de capturas, preparación y escritura Silver. Estas funciones se validaron en PostgreSQL aislado y la vista previa local preparó las 30 observaciones archivadas.

Se incorporaron las funciones compartidas de media FIX, referencias mensuales en MXN/t y variaciones por fecha exacta. La vista previa Gold produjo tres referencias para septiembre desde las capturas archivadas. Posteriormente se implementaron la persistencia Gold y el publicador transaccional. El coordinador histórico conectó la extracción con esas funciones y recorrió el periodo elegido con HTTP simulado y PostgreSQL aislado. Se confirmó después que la ejecución histórica real terminó con los resultados esperados. Sobre esa base se implementó el comando incremental independiente, con revisión reciente configurable y publicación mediante las mismas transformaciones.

La salida real registrada confirmó una revisión incremental satisfactoria sin cambios. A continuación se completaron, en una entrega conjunta, la recuperación explícita, los reprocesos de periodos publicados y el dashboard de tres visualizaciones conectado a PostgreSQL. La lectura analítica y la publicación mantienen responsabilidades separadas.

Se confirmó el funcionamiento y la apariencia del dashboard. La etapa final incorporó el wheel, un entorno de automatización independiente, el registro de una tarea diaria y su comprobación de solo lectura desde Windows. También se verificó el producto real, se exportaron los resultados analíticos y se prepararon el runbook y la documentación técnica. Los cambios finales se agrupan en los commits de documentación y automatización registrados al final de esta bitácora.

Este documento registra el avance de implementación y sus verificaciones. El [perfilamiento inicial](Perfilamiento_inicial.md) describe la muestra, los [resultados analíticos](RESULTADOS_ANALISIS_ES.md) y la [validación final](VALIDACION_FINAL_ES.md) presentan los datos y comprobaciones del cierre con sus respectivos alcances.

## 2. Avance registrado

| Etapa | Trabajo realizado | Referencia |
|---|---|---|
| Entorno | Registro de Python 3.12.4, entorno virtual y exclusión de archivos locales. | `0795d45` |
| Alcance | Documentación del objetivo, las capas, las cargas independientes y la organización por responsabilidades. | `2a47d73` |
| Fuentes | Catálogo de los tres precios de granos y del FIX de determinación, con unidades y frecuencias esperadas. | `b952419` |
| Configuración | Lectura de credenciales privadas, prioridad del entorno y comprobaciones con valores ficticios. | `bd81adc` |
| Comunicación | Cliente HTTP autenticado y consulta de metadatos de las cuatro series. | `1e39563` |
| Contratos | Validación de estructura, identidad, título, unidad, frecuencia y clasificación de las fuentes. | `f8bcdb5` |
| Selección temporal | Interpretación de fechas, disponibilidad declarada y ventanas para un mes cerrado común. | `89303ae` |
| Extracción y perfil | Consulta de observaciones, captura por ejecución y controles de fechas, valores, duplicados y cobertura mensual. | `4c894c6` |
| Evidencia inicial | Revisión de la muestra real, reproducción del perfil y conservación de las capturas que sustentan sus resultados. | `4c894c6` |
| Modelo y calidad | Diseño de ocho entidades, diccionario de campos y reglas de publicación para histórico e incremental independientes. | `6485538` |
| Preparación PostgreSQL | SQL inicial, tabla técnica de versiones, conexión privada, catálogo y verificación de solo lectura. | `90381bf` |
| Documentación de ejecución | README en inglés con resumen, requisitos, preparación de PostgreSQL y comandos, seguimiento del desarrollo conservado en esta bitácora. | `7620212` |
| Persistencia y preparación Silver | Registro de intentos, capturas y DQ, verificación de integridad, conversión a tipos comunes y escritura por clave natural. | `57929ee` |
| Calendario y transformaciones Gold | Referencia bancaria 2026, regla DQ-09, dependencias mensuales, media FIX, referencias MXN/t y variaciones. | `f19cc14` |
| Publicación transaccional | Escritura Gold, procedencia Silver, validación global, bloqueo del producto y confirmación conjunta de capas, watermark y éxito. | `d995cb5` |
| Coordinación histórica | Periodo explícito, referencias 2009–2026, consultas anuales, reintentos, perfil consolidado y publicación hasta Gold. Ejecución real confirmada. | `67f149a` |
| Coordinación incremental | Plan según watermark y fuentes, revisión configurable, cierre sin trabajo y reutilización modular de captura y publicación. | `50fa914` |
| Recuperación y reproceso | Decisión bajo bloqueo, intento nuevo con originales íntegros y correcciones explícitas dentro del histórico. | `7d3d0b9` |
| Análisis y visualización | Lectura consistente de Gold, métricas decimales, tres gráficos y filtros en Streamlit. | `7d3d0b9` |
| Distribución y automatización | Wheel 1.0.0, entorno independiente, preflight de solo lectura, logs y tarea diaria registrada. | `e404f41`. |
| Validación y entrega | Pruebas finales, verificación instalada, análisis real y runbook. | Commit documental de cierre. |

## 3. Organización de la implementación

El código se distribuye por responsabilidad mediante funciones y paquetes. Las reglas de calidad se mantienen separadas del transporte y de la coordinación de la extracción.

| Componente | Responsabilidad implementada |
|---|---|
| `common/` | Configuración privada, fechas, operaciones de calendario y política decimal compartida. |
| `clients/` | HTTP, autenticación, tiempos de espera, reintentos acotados y errores controlados. |
| `sources/` | Catálogo, contratos, consultas, selección de ventanas y referencias bancarias anuales. |
| `extraction/` | Conservación de capturas de muestra y de los fragmentos solicitados por ambas cargas. |
| `quality/` | Interpretación decimal, perfil, aceptación, cobertura, continuidad, procedencia y comparación de resultados. |
| `persistence/` | Conexión, esquema, catálogo, intentos, capturas, DQ, Silver, Gold y watermark. |
| `transformations/` | Preparación Silver, media FIX, referencias MXN/t, variaciones y vistas previas locales. |
| `orchestration/` | Coordinadores independientes de histórico, incremental, reproceso y recuperación, captura, perfil, publicación y cierre compartidos, comprobación de estado y ejecutor programado. |
| `tests/` | Casos sin servidor y SQL, capturas ficticias y ejecutor con integración explícita. |
| `app/` | Consulta de solo lectura, indicadores, gráficos e interfaz del dashboard. |
| `.streamlit/` | Tema visual y estadísticas de uso desactivadas. |
| `scripts/` | Construcción limpia, instalación, registro y prueba del scheduler, exportación de resultados. |

El flujo implementado consulta los metadatos, determina las ventanas, solicita las observaciones, conserva el JSON recibido y aplica el contrato y las reglas de perfil. Los números se interpretan directamente desde texto con `Decimal`, manteniendo la precisión disponible en las fuentes.

El [modelo de datos](MODELO_DATOS_ES.md), el [diccionario](DICCIONARIO_DATOS_ES.md) y el [catálogo DQ](REGLAS_CALIDAD_ES.md) especifican las responsabilidades de persistencia y transformación. El preparador implementa ocho tablas del modelo y `ops.schema_migrations` como control técnico. Las garantías de carga y publicación siguen diferenciadas de la exploración y de la preparación del esquema.

## 4. Captura y trazabilidad

Cada diagnóstico crea una carpeta independiente en `data/bronze/samples/`. Una ejecución completa conserva cuatro registros de metadatos, cuatro respuestas de observaciones y un perfil consolidado. Las capturas incluyen proveedor, código de serie, instante UTC y ventana de consulta.

Las respuestas de observaciones se guardan antes de comprobar su contrato. Si una consulta o una estructura fallan, las capturas previas permanecen y la ejecución no genera el perfil final. Los archivos existentes se preservan mediante creación exclusiva.

La ejecución inicial examinada es `20261103T215523120075Z_7bb854f46f16499eb08a3e2a98098072`, con fecha de referencia 2026-11-03 y mes final de muestra 2026-09. Sus nueve archivos se conservaron en [evidencias de perfilamiento inicial](evidencias/perfilamiento_inicial/manifest.json). El manifiesto identifica la ejecución, las verificaciones y las sumas SHA-256 de cada archivo.

Las capturas operativas permanecen excluidas de Git. La copia seleccionada para documentar el perfil inicial se conserva dentro de `docs/evidencias/` y acompaña al informe.

## 5. Verificaciones y resultados

| Tipo de verificación | Evidencia disponible |
|---|---|
| Pruebas sin servidor | 163 casos aprobados, incluidos contratos del wheel y ejecución programada con propagación de errores y timeout. |
| Pruebas SQL | 91 casos aprobados en PostgreSQL 18.6 aislado, incluido el estado de solo lectura, cero omisiones. |
| Consultas reales previas | Confirmación de acceso, contratos de metadatos, disponibilidad y propuesta de ventanas de las cuatro series. |
| Muestra real | 3 observaciones por grano de julio a septiembre de 2026 y 21 observaciones FIX de septiembre: 30 registros en total. |
| Reproducción del perfil | Los cuatro perfiles recalculados desde las capturas coinciden con `profile.json`. |
| Calidad observada | Cero ausentes, formatos inválidos, valores no positivos, fechas incompatibles, fechas fuera de ventana y duplicados. |
| Cobertura mensual | Tres meses esperados y tres meses con valores utilizables en cada grano. |
| Cobertura diaria | Septiembre de 2026: igualdad de las 21 fechas esperadas y recibidas, sin faltantes, inesperadas o duplicadas. |
| Preparación del proyecto | Se confirmó la ejecución del preparador y su verificación de solo lectura, quedó registrada en `90381bf`. |
| Preparación Silver real | Las 30 observaciones archivadas se prepararon como `date` y `Decimal` sin consultar APIs ni escribir en la base del proyecto. |
| Transformación Gold real | 24 entradas del mes seleccionado: tres precios y 21 FIX. Se produjeron una media y tres referencias MXN/t en memoria. |
| Publicación SQL con datos ficticios | Inicialización, repetición, revisiones, ampliación continua, visibilidad entre sesiones y reversión conjunta de capas y control. |
| Histórico técnico completo | Enero de 2009 a septiembre de 2026 con HTTP simulado: 76 capturas, 5,102 observaciones Silver, 213 agregados FIX y 639 referencias Gold. |
| Histórico real | Ejecución del mismo periodo con resultados esperados confirmada, sus capturas operativas permanecen locales. |
| Incremental técnico completo | Sobre el histórico ficticio, incorporación de octubre con consulta de julio–octubre: ocho peticiones lógicas, 5,127 observaciones Silver, 214 medias FIX y 642 referencias Gold. |
| Incremental real sin cambios | Salida registrada: julio–septiembre de 2026, 74 observaciones revisadas, cero escrituras y watermark conservado, estado `succeeded`. |
| Dashboard | Tres gráficos y filtros comprobados con AppTest y PostgreSQL aislado, funcionamiento y apariencia confirmados posteriormente. |
| Estado real | Preflight desde el wheel: 5,102 Silver, 213 meses FIX y 639 referencias, mediante lecturas y verificación de originales. |
| Wheel instalado | Recorrido completo con datos ficticios desde `site-packages`, recursos incluidos y entorno sin dependencias del dashboard. |
| Scheduler real | Tarea diaria registrada, tarea temporal de preflight terminó con código cero y fue retirada, sin carga ni escrituras SQL. |
| Análisis exportado | 201 meses comunes de 2010-01 a 2026-09, informe numérico del Gold real. |

Las pruebas simuladas verifican el comportamiento del código. La muestra real aporta evidencia sobre los registros efectivamente recibidos. Ambas verificaciones tienen alcances distintos y se documentan por separado.

El [resumen original de preparación PostgreSQL](evidencias/preparacion_postgres/validacion.json) registra 83 pruebas aprobadas, sin fallos ni omisiones, con Python 3.12.4 y Psycopg 3.3.7. Cada prueba SQL utilizó una base desechable propia dentro de una instancia temporal local, que se detuvo al terminar. La base indicada en el `.env` del proyecto no se utilizó para esas pruebas. En ese avance, sin conexión explícita de prueba se omitían los 11 casos SQL.

La ampliación Silver está sustentada por [108 pruebas aprobadas](evidencias/persistencia_silver/validacion.json) y una [vista previa normalizada](evidencias/persistencia_silver/vista_previa.json). De ellas, 22 utilizaron PostgreSQL aislado, la instancia temporal se cerró. Se comprobaron inserción, repetición sin cambios, revisión de una fila, preservación de procedencia, detección de archivos alterados y rollback decidido por el coordinador. En esa etapa, una ejecución sin conexión de prueba omitía esos 22 casos. Los recuentos anteriores son hitos históricos, el cierre registra 254 casos, incluidos 91 SQL.

### 5.1. Ejecución de la validación y generación de evidencias

Se preparó una instancia PostgreSQL temporal mediante los binarios `initdb.exe` y `pg_ctl.exe`. El clúster se ubicó en `data/verification/`, escuchó en `127.0.0.1` con un puerto separado del servicio del proyecto y utilizó una cuenta de prueba. Cada caso SQL creó y eliminó su propia base `grain_test_<uuid>`, con datos ficticios para comprobar las operaciones y restricciones.

Desde PowerShell se ejecutaron scripts auxiliares de Python que establecieron `TEST_DATABASE_URL` hacia esa instancia antes de cargar las pruebas. La selección se realizó con `unittest.defaultTestLoader.discover("tests")` y la ejecución con `unittest.TextTestRunner`. Se obtuvieron del resultado los casos ejecutados, fallos, errores, omisiones y aprobación global, se añadieron las versiones del entorno, la fecha UTC y el checksum del SQL calculado por `schema_resource()`.

Los resultados se serializaron como JSON. La comprobación del preparador produjo `preparacion_postgres/validacion.json` con 83 pruebas aprobadas, la ampliación de persistencia produjo `persistencia_silver/validacion.json` con 108. Corresponden a dos verificaciones realizadas en momentos distintos del desarrollo. Los resúmenes conservados están vinculados en esta sección y documentan sus respectivos entornos y alcances.

Para generar `persistencia_silver/vista_previa.json` se procesaron las cuatro capturas reales de observaciones conservadas en `docs/evidencias/perfilamiento_inicial/`. Los scripts invocaron `read_capture`, `get_series`, `read_observations` y `prepare_observations`, comprobaron los hashes contra el manifiesto y verificaron que las fechas fueran objetos `date` y los valores fueran `Decimal`. Se prepararon 30 observaciones y se conservaron sus referencias de origen. Al exportar el JSON, las fechas se expresaron mediante `isoformat()` y los decimales mediante `str()`, manteniendo sus dígitos.

También se ejecutó el comando `python -X utf8 -m grain_pipeline.transformations.silver` para comprobar la vista previa en terminal. La normalización de las capturas archivadas se realizó en memoria, sin consultas nuevas a las APIs ni escritura de esos registros en la base del proyecto. La cobertura bancaria FIX permaneció identificada como pendiente.

Al terminar las pruebas se cerró la instancia temporal. Los informes de preparación PostgreSQL y persistencia Silver se exportaron mediante scripts ejecutados en línea durante la sesión de PowerShell, esos generadores no quedaron incorporados como archivos `.py` reutilizables. Las pruebas y funciones invocadas forman parte del código del proyecto. Los archivos de esas etapas en `docs/evidencias/` son registros de sus ejecuciones y no una exportación automática de los comandos de preparación o vista previa. Las etapas posteriores incorporaron exportaciones explícitas mediante `tests.run --report`, `gold_preview --output` y los scripts de entrega descritos en sus secciones.

### 5.2. Referencia bancaria y verificación de las transformaciones Gold

Se revisó la definición de FIX de determinación de Banxico y la publicación de las disposiciones de cierre bancario 2026 de la CNBV en el DOF. Se cotejaron las fechas con la relación de la Asociación de Bancos de México. Las fuentes, fechas de publicación y revisión, fines de semana y cierres quedaron registrados en `sources/calendars/2026.json`. La referencia se identificó mediante versión y SHA-256 con saltos de línea normalizados.

Se separó la lectura del calendario de la regla `DQ-09`. Esta última comparó las fechas FIX utilizables con las esperadas y conservó los faltantes, inesperados, duplicados y registros inválidos. Los años sin referencia revisada quedaron como `pending`, condición que impide generar el agregado. La regla se probó también con 21 filas cuyo conteo coincide, pero cuyas fechas no corresponden al calendario: la evaluación rechazó el conjunto incompatible.

Se implementaron funciones independientes para validar el conjunto Silver, agregar FIX y construir Gold. Se exigieron meses cerrados, claves únicas y los tres precios por mes. Los cálculos utilizaron contextos decimales locales de 34 dígitos y `ROUND_HALF_EVEN`. Las variaciones se asociaron al mes anterior y al mismo mes del año previo, una ausencia interior bloqueó el cálculo. Una revisión ficticia de agosto comprobó el recálculo de su referencia y de la variación dependiente de septiembre.

La suite completa se ejecutó con Python 3.12.4 mediante un script Python en línea desde PowerShell, con `unittest.TestLoader().discover("tests")` y `unittest.TextTestRunner`. Para esta ejecución se retiró `TEST_DATABASE_URL` únicamente del entorno del proceso de prueba. Se descubrieron 130 casos, se ejecutaron 108 sin fallos ni errores y se omitieron los 22 que requieren PostgreSQL. Los contadores y el contexto de ejecución se exportaron a [validacion.json](evidencias/calendario_gold/validacion.json). No se inició una instancia ni se repitieron las pruebas SQL del avance Silver.

La vista previa real se ejecutó mediante el comando incorporado al proyecto:

```powershell
python -X utf8 -m grain_pipeline.transformations.gold_preview --month 2026-09 --sample-dir docs/evidencias/perfilamiento_inicial --bronze-root docs/evidencias/perfilamiento_inicial --output docs/evidencias/calendario_gold/vista_previa.json
```

La carpeta de destino se creó previamente. El comando validó las cuatro capturas completas, preparó Silver y seleccionó 24 entradas de septiembre. Certificó las 21 fechas FIX y obtuvo una media de `17.26401904761904761904761904761905` MXN/USD. Las referencias resultantes fueron aproximadamente 4,090.12 MXN/t para maíz, 4,261.65 para trigo y 8,316.46 para soya. MoM y YoY quedaron nulos al no incluir comparadores en esta vista previa de un mes.

El [informe Gold](evidencias/calendario_gold/vista_previa.json) conservó valores completos, hashes de origen y métricas de calendario. Su exportación quedó disponible con `--output` en el módulo `gold_preview.py`, que rechaza sobrescribir archivos existentes. No se consultaron APIs, no se escribieron observaciones en PostgreSQL y no se modificaron watermarks. Las capturas, el perfil y las evidencias anteriores permanecieron intactos. La [guía de calendario y Gold](GUIA_CALENDARIO_Y_GOLD_ES.md) documenta las funciones, los comandos y el alcance de la verificación.

### 5.3. Persistencia Gold y verificación de la publicación atómica

Se añadieron módulos separados para las reglas del intervalo publicado, la escritura Gold, la lectura del watermark y el bloqueo del producto. Se incorporó `orchestration/` para coordinar la preparación y las transacciones mediante funciones. El recurso SQL inicial permaneció sin modificaciones y no se requirieron dependencias nuevas.

Se revalidaron los metadatos desde sus registros Bronze y se reunieron las observaciones de las cuatro series. Se registraron controles por captura y de conjunto, incluidos duplicados entre fragmentos, meses de granos faltantes y cobertura FIX mensual. El conjunto recibido debió estar completo por sí mismo antes de combinarse con Silver vigente. También se comprobó que cada fila Silver coincidiera con su captura íntegra de la misma serie y fecha.

La preparación confirmó sus resultados DQ antes de modificar las capas. Una segunda transacción actualizó Silver, reconstruyó Gold para el intervalo publicado y confirmó watermark y estado exitoso juntos. Las escrituras Gold conservaron la auditoría de filas sin cambios. Un bloqueo de sesión mantuvo la exclusión entre esas transacciones. Los fallos de publicación revirtieron sus escrituras y se registraron después con etapa y resumen controlado.

Se construyó un ejecutor reutilizable en `tests/run.py`. Con `--postgres` leyó la conexión de prueba antes del descubrimiento, validó su prefijo y exigió cero omisiones. La clave de producción no se utilizó como alternativa. El parámetro `--report` permitió exportar contadores reales y los identificadores de los casos SQL ejecutados sin sobrescribir informes existentes.

Primero se ejecutaron 18 pruebas SQL nuevas en la instancia temporal y finalizaron correctamente. Después de completar las comprobaciones de visibilidad, duplicados globales y protección del finalizador, se ejecutó la suite completa mediante `tests.run` con `--postgres --report`. La conexión se proporcionó en el entorno del proceso hacia el clúster local aislado, sin leer el `.env` real.

El resultado fue de **161 pruebas aprobadas: 118 sin servidor y 43 SQL**, con cero fallos, errores u omisiones, en Python 3.12.4 y PostgreSQL 18.6. Cada caso SQL utilizó una base desechable y capturas ficticias. Una segunda conexión confirmó que el estado anterior permanecía visible hasta el commit. Se inyectaron errores después de escribir Gold y después de actualizar watermark y éxito, todas esas modificaciones se revirtieron juntas. La revisión ficticia de agosto también actualizó la variación dependiente de septiembre.

El ejecutor generó el resumen en una ruta local nueva. El script auxiliar en línea inició y detuvo la instancia temporal y, al terminar correctamente, añadió ese contexto al [informe de publicación](evidencias/publicacion_gold/validacion.json). La base del proyecto y las evidencias reales previas permanecieron sin modificaciones. La [guía de publicación Gold](GUIA_PUBLICACION_GOLD_ES.md) registra los contratos, resultados, comandos y límites de recuperación.

### 5.4. Coordinador histórico y periodo seleccionado

Se consultó la matriz de alineación conservada en el proyecto original, `DE.pdf` no estaba disponible en esta copia. Se mantuvieron los requisitos registrados de integración de dos fuentes, ETL en Python, persistencia, controles, visualización y entrega. Se definió reconstruir el intervalo 2009-01 a 2026-09 mediante el comando histórico explícito.

Se incorporaron diecisiete referencias anuales adicionales a partir de la tabla curada del proyecto original, cuya revisión estaba registrada el 2026-11-02. Se conservaron la fecha de revisión, el commit de procedencia, la copia pública de la tabla y sus hashes. Se cotejaron los registros de publicación disponibles en SIDOF y se preservaron los cierres extraordinarios documentados de 2010 y 2024. El recurso 2026 previo permaneció intacto. El [manifiesto histórico](evidencias/calendario_historico/manifest.json) registró 213 meses y 4,463 fechas FIX esperadas, sin presentarlas como observaciones nuevamente consultadas.

Se separaron las ventanas anuales, las reglas de disponibilidad, las funciones de captura y el perfil consolidado. El coordinador adquirió el bloqueo del producto desde la planificación, registró el intento y confirmó cada captura antes de aplicar sus contratos. Se exigió una base sin watermark para la inicialización histórica. Las peticiones HTTP se realizaron con la conexión SQL sin transacción abierta, esta condición se comprobó durante la integración.

El cliente HTTP incorporó hasta tres intentos para fallos transitorios, con esperas acotadas y tratamiento de `Retry-After`. Las respuestas se cerraron antes de esperar. Los contratos y errores permanentes siguieron siendo bloqueantes. Las pruebas separaron el comportamiento de un único intento de los escenarios de recuperación y agotamiento.

La integración de PostgreSQL recorrió primero diez casos nuevos con HTTP simulado y terminó correctamente. Después se ejecutó la suite completa mediante `tests.run --postgres --report`, usando la conexión del clúster temporal en el entorno del proceso. El resultado fue de **186 pruebas aprobadas: 133 sin servidor y 53 SQL**, sin fallos, errores ni omisiones. El [informe de carga histórica](evidencias/carga_historica/validacion.json) conserva el resultado y distingue los datos ficticios utilizados.

El caso del intervalo completo realizó 76 llamadas HTTP simuladas y publicó 639 precios ficticios de 100 USD/t y 4,463 FIX ficticios de 20 MXN/USD. Se comprobaron 213 agregados, 639 referencias y 603 variaciones YoY con comparador. Otros casos verificaron fallos de red, metadatos incompatibles, respuestas parciales, cobertura incompleta y rechazo de una segunda inicialización. El comando de terminal también se probó con configuración ficticia y una base desechable.

La instancia temporal se detuvo al terminar. No se leyó el `.env` real ni se escribió en la base del proyecto. La ejecución con las APIs reales quedó documentada en la [guía histórica](GUIA_CARGA_HISTORICA_ES.md), junto con sus archivos de plan, capturas, manifiesto, perfil y resultado de publicación. El README mantuvo su función de instrucciones de ejecución en inglés.

Posteriormente, se registró la confirmación de la ejecución histórica real con los resultados esperados. El avance quedó guardado en `67f149a`. La comprobación independiente de solo lectura del producto real se realizó durante el cierre, como registra la sección 5.9.

### 5.5. Coordinador incremental y revisión de publicaciones

Se implementó un comando independiente que exige el watermark histórico antes de consultar las APIs. La planificación combina la disponibilidad de las cuatro series con el último mes cerrado en la zona de operación. La revisión predeterminada comprende los últimos tres meses publicados y todos los meses nuevos, se permite configurarla entre cero y doce y establecer un corte mensual opcional. Una regresión de disponibilidad, la falta de calendario revisado o una cobertura insuficiente bloquean la publicación.

Se trasladaron las funciones de captura a `extraction/captures.py` y las reglas temporales compartidas a `quality/windows.py`. Se separaron las consultas y registros, los artefactos y el cierre de fallos en módulos de orquestación reutilizables. El histórico conservó su interfaz y sus archivos. El incremental no invoca ese coordinador ni inicializa el producto de manera implícita. No se añadieron clases de aplicación, requisitos de instalación ni cambios en el SQL inicial.

La extracción quedó limitada a la ventana seleccionada. El publicador reutiliza Silver validado para reconstruir Gold sobre todo el intervalo y mantener comparadores MoM y YoY exactos. Se actualizan únicamente los valores que cambian. Con revisión desactivada y sin meses seleccionados se comprueban las capturas, Silver y Gold vigentes antes de registrar `skipped`, el watermark y las tablas de hechos permanecen iguales. Una revisión ejecutada puede cerrar `succeeded` con cero escrituras.

La verificación comenzó con los casos específicos de planificación y de ambos coordinadores. Después se ejecutó `tests.run --postgres --report` con la conexión del clúster temporal en el entorno del proceso y una ruta de configuración que no corresponde al `.env` real. La suite completa terminó con **209 pruebas aprobadas: 141 sin servidor y 68 SQL**, sin fallos, errores ni omisiones. El [informe incremental](evidencias/carga_incremental/validacion.json) registra los casos SQL y el alcance de la comprobación.

Las pruebas comprobaron revisiones de granos y FIX, recálculo de variaciones dependientes, recuperación continua de varios meses, cambio de año, cierre sin trabajo, integridad de la publicación previa y reversión después de modificar watermark y éxito. Un caso partió del histórico ficticio 2009-01 a 2026-09 y agregó octubre mediante ocho consultas lógicas, terminando con 5,127 observaciones Silver, 214 medias FIX y 642 referencias Gold. Los datos de esas APIs simuladas fueron valores ficticios, no constituyen una carga real adicional.

El clúster aislado se detuvo al terminar. No se leyó el `.env` real ni se escribió en la base del proyecto. Se actualizó el README en inglés, la documentación del modelo y las guías de ejecución, la [guía incremental](GUIA_CARGA_INCREMENTAL_ES.md) reúne parámetros, comportamiento esperado y consultas de control.

Se registró después la salida de `2d5eef1b-603e-4d13-97ff-360fa54e0a81`: las cuatro fuentes se consultaron para julio–septiembre de 2026, se recibieron 74 observaciones y no se modificaron Silver ni Gold. El watermark permaneció en septiembre y el intento terminó `succeeded`. Se registra como comprobación real de una revisión sin cambios, sin atribuirle una ampliación del histórico.

### 5.6. Recuperación y reproceso de periodos publicados

Se incorporaron reglas puras para decidir la recuperación desde el estado durable y para limitar el reproceso al intervalo publicado. La persistencia de recuperación se mantuvo en un módulo aparte. El coordinador obtiene el bloqueo del producto antes de cerrar un huérfano, conserva los intentos terminados y abre un identificador nuevo cuando reutiliza capturas completas. `CTL-05` registra la operación, el origen y los identificadores reutilizados, los archivos conservan su propietario original.

Las capturas incompletas o anteriores a otra publicación producen una instrucción de extracción nueva. Se evita restaurar valores antiguos sobre correcciones posteriores. Las recuperaciones repiten hash, contrato, DQ y publicación, no consultan APIs. Una recuperación que falla conserva sus vínculos para poder tratar su propio intento después. El cierre del huérfano se confirma antes del nuevo trabajo.

El reproceso recibe meses explícitos dentro del histórico, consulta las fuentes actuales y reutiliza las funciones de captura y publicación. Mantiene los límites del producto y recalcula Gold completo. La prueba de julio de 2025 modificó una observación y tres filas Gold: la referencia del mes, el MoM siguiente y el YoY del año posterior. La política quedó documentada en la [guía de recuperación y reprocesos](GUIA_RECUPERACION_Y_REPROCESOS_ES.md).

### 5.7. Análisis y dashboard conectado a PostgreSQL

Se añadieron `app/queries.py`, `app/analytics.py`, `app/charts.py` y `app/streamlit_app.py`, separando consulta, cálculos, gráficos e interfaz. La consulta fuerza solo lectura, aislamiento repetible y esperas limitadas. Se permite una cuenta independiente mediante `READONLY_DATABASE_URL`, solo cuando esa clave está ausente se utiliza `DATABASE_URL`, con las mismas restricciones transaccionales. Una clave definida pero vacía exige corregirse.

El contrato analítico comprueba los tres granos en cada mes, cobertura FIX, producto y variaciones antes de mostrar resultados. Se implementaron índices base cien, atribución simétrica de los cambios mensuales, comparación acumulada y frecuencia de ahorro cancelado. Los cálculos conservan `Decimal`, la conversión numérica se limita a la presentación. Las unidades, comparadores y alcance nominal se explican en la interfaz y en la [documentación analítica](ANALISIS_Y_DASHBOARD_ES.md).

Se instalaron y fijaron Streamlit 1.66.1 y Plotly 7.1.0. Las pruebas iniciales detectaron que el entorno vacío eliminaba variables que Windows necesitaba para AppTest, se corrigió el aislamiento de la configuración de pruebas. La comprobación de DLL de la interfaz requirió ejecutar la verificación fuera del aislamiento restringido. La suite completa posterior aprobó **243 pruebas: 156 sin servidor y 87 SQL**, sin fallos, errores ni omisiones. El [informe conjunto](evidencias/recuperacion_dashboard/validacion.json) conserva los casos y versiones.

Se comprobaron permisos exclusivamente de lectura, rechazo de DML con una cuenta administradora, consistencia durante una publicación concurrente y filtros de la interfaz usando consultas reales a bases desechables. Las pruebas de recuperación verificaron bloqueo activo, hash alterado, archivo ausente, repetición, antigüedad de capturas y rollback después de modificar watermark y éxito. No se leyó el `.env` real ni se modificó la base del proyecto, el SQL inicial y los calendarios permanecieron intactos.

Se preparó además una vista previa local con 33 meses ficticios. Computer Use detuvo la revisión visual al no poder identificar con suficiente confianza la URL actual de Windows. Esta comprobación no se presenta como aprobada: el [registro de interfaz](evidencias/recuperacion_dashboard/revision_interfaz.json) conserva la limitación y el cierre del servidor, la base de vista previa y el clúster temporal. La validación de interacción mediante AppTest sí terminó correctamente.

El avance quedó guardado en `7d3d0b9`. Posteriormente, se confirmó el funcionamiento y la apariencia del dashboard. Esa confirmación se distingue del intento de Computer Use y conserva el registro original de aquella limitación.

### 5.8. Empaquetado e instalación independiente

Se definió `pyproject.toml` con la versión 1.0.0, las entradas de consola, las cuatro dependencias de datos y el extra opcional del dashboard. Se incluyeron explícitamente SQL y calendarios. El constructor preparó una copia nueva y mínima para evitar secretos y restos de builds anteriores. La instalación inicial detectó la herencia de permisos del temporal de construcción, se corrigió en el wheel generado y en el constructor para que heredara los permisos del directorio de salida.

Se creó `.venv-automation` y se instaló el wheel sin Streamlit ni Plotly. La comprobación importó el producto desde `site-packages` con Python aislado, preparó una base UUID de prueba y recorrió histórico, incremental, reproceso, recuperación y estado con HTTP ficticio. El [recibo instalado](evidencias/entrega_final/wheel_installation.json) conserva la evidencia inicial. La verificación del artefacto final incluye las ocho entradas de consola y se relaciona con su hash de construcción.

El Control de aplicaciones de Windows bloqueó los lanzadores `.exe` generados por pip. Se mantuvo la política existente y se verificaron sus funciones de entrada con el intérprete instalado. La tarea y los comandos compatibles utilizan `python -I -m`, que ya había completado el recorrido y el smoke del scheduler. La evidencia diferencia la comprobación de funciones de la ejecución de lanzadores nativos.

Se añadió `state.py` para comprobar el producto y sus originales sin modificar SQL ni consultar APIs. El lector de watermark permite omitir el bloqueo de escritura en esta comprobación, conservando su comportamiento previo en las cargas. La suite completa aprobó **254 pruebas: 163 sin servidor y 91 SQL**, sin fallos, errores ni omisiones, el [informe final](evidencias/entrega_final/validacion.json) conserva los casos. El clúster de pruebas se detuvo y sus bases desechables se retiraron.

### 5.9. Ejecución programada en Windows

Se separaron el ejecutor Python y los scripts de instalación y registro. El proceso programado importa el wheel con `-I`, crea logs UTF-8 exclusivos, conserva el código de salida y limita el tiempo de ejecución. Un timeout devuelve `124` y requiere consultar el estado durable antes de recuperar. No invoca el histórico.

El preflight instalado verificó el producto real hasta septiembre de 2026: 5,102 observaciones Silver, 213 medias FIX y 639 referencias. Estas lecturas utilizaron la configuración privada mediante el cargador del proyecto, sin imprimir ni copiar sus credenciales, y no modificaron las capas.

Se validó el XML y se registró `GrainPipelineLearningIncremental`, diariamente a las 20:00 de Ciudad de México. La tarea usa una cuenta de ejecución con sesión iniciada y privilegios limitados, sin guardar su contraseña, y fija el primer disparo en una fecha futura. El registro archivado indicaba como siguiente ejecución el 4 de noviembre de 2026 a las 20:00, sin acreditar disparos posteriores. El [registro público](evidencias/entrega_final/automation.json) omite identidad y rutas privadas, el XML completo permanece local y excluido de Git.

Una tarea temporal ejecutó el mismo paquete en modo `--check-only` sobre el producto real y terminó con código cero. Después fue retirada sin reemplazar la tarea diaria. La [evidencia del scheduler](evidencias/entrega_final/scheduler_smoke.json) distingue ese preflight real del primer disparo futuro de carga incremental. Los procedimientos de operación y recuperación quedaron en la [guía de automatización](GUIA_AUTOMATIZACION_ES.md) y el [runbook](RUNBOOK_ES.md).

### 5.10. Análisis real y entrega final

Se exportó el Gold real mediante una instantánea de solo lectura para 2010-01 a 2026-09. El [informe analítico](RESULTADOS_ANALISIS_ES.md) presenta cambios acumulados de 90.93% en maíz, 98.36% en trigo y 80.97% en soya. Las frecuencias de ahorro cancelado fueron 15/97, 14/101 y 16/97, respectivamente, con denominadores y comparadores explícitos. No se realizaron nuevas peticiones a las APIs para producir estos resultados.

La [validación de cierre](VALIDACION_FINAL_ES.md) relaciona los criterios del plan, las pruebas aisladas y las comprobaciones del proyecto real. El README conserva instrucciones en inglés, sin convertirse en bitácora. Se reconocen las fuentes y la asistencia de IA. El cierre se organiza por documentación técnica, automatización y documentación final.

### 5.11. Revisión de coherencia documental

En la revisión documental del entorno de origen se revisaron los 24 archivos Markdown entonces disponibles, contrastando sus descripciones con el código, el SQL, los metadatos del paquete y las evidencias conservadas. Se corrigieron referencias que todavía presentaban como futuras la publicación Gold, las cargas independientes, la recuperación y la automatización. El plan mantuvo su carácter de propuesta inicial, el modelo y las guías describen los componentes implementados.

Los recuentos de pruebas de cada etapa se identificaron como resultados históricos. La validación del cierre permanece en 254 casos aprobados, incluidos 91 SQL, según su informe original, esta revisión documental no constituye una nueva ejecución de la suite. También se distinguieron las 30 observaciones de la muestra, las 74 de la revisión incremental real y las 5,102 del histórico, así como el diagnóstico inicial FIX pendiente y su certificación bancaria posterior.

Se comprobaron los enlaces locales, las rutas de código y las opciones declaradas de los comandos. Se alinearon las instrucciones de pruebas, configuración de lectura, contenido del wheel y operación programada, la recuperación permanece explícita. Se corrigieron acentos dañados. Se unificó la redacción impersonal de las verificaciones y se sustituyeron los puntos y coma de la prosa por comas. Los ejemplos de código conservaron su sintaxis. Las evidencias originales conservaron sus hashes. La revisión modificó únicamente documentación del proyecto y se incorpora al cierre documental.

## 6. Estado de las capas y cargas

| Frente | Estado al corte |
|---|---|
| Bronze | Muestras reales conservadas y captura por ventanas compartida entre histórico e incremental. |
| Silver | Compartida por cargas, reprocesos y recuperación, histórico real confirmado y revisión incremental real sin cambios registrada. |
| Gold | Transformaciones y publicación compartidas, referencias, comparadores y lectura analítica verificados. |
| Carga histórica | Comando inicial independiente y periodo 2009-01 a 2026-09. Ejecución real con resultados esperados confirmada. |
| Carga incremental | Comando independiente verificado, revisión real de julio–septiembre completada sin cambios. Ampliación comprobada con HTTP simulado. |
| Recuperación y reproceso | Comandos explícitos implementados y verificados con PostgreSQL aislado. |
| Persistencia y control | Publicador, bloqueo de sesión, diagnóstico durable, watermark y vínculos de recuperación implementados. |
| Visualización | Tres gráficos conectados, AppTest aprobado y funcionamiento confirmado, análisis real exportado. |
| Automatización | Verificación archivada del entorno de origen: wheel instalado, preflight y smoke de solo lectura aprobados, tarea diaria registrada. La integración local no realiza ese despliegue. |
| Entrega | README, modelo, DQ, runbook y evidencias preparados. |

La extracción de muestra es un diagnóstico de fuentes. Las cargas reales conservan sus propias capturas, métricas y estado durable. El dashboard consulta exclusivamente el producto publicado.

## 7. Continuidad prevista

El alcance de implementación quedó preparado y comprobado. La operación posterior requiere conservar PostgreSQL y Bronze, revisar los resultados de la tarea y agregar referencias bancarias antes de publicar un nuevo año. El primer disparo futuro no se presenta como carga programada ya completada.

Los archivos finales se incorporan al cierre documental. No se modifica el carácter general del plan inicial ni se reemplazan las evidencias originales.

Esta bitácora se actualizará con cada avance, su referencia de commit, la evidencia obtenida y los pendientes que afecten a las etapas posteriores.

## 8. Historial del repositorio e integración limpia

El historial siguiente corresponde a los commits del repositorio actual. Los cambios de empaquetado, automatización y entrega se integran el 4 de noviembre de 2026 y se registran en los commits de cierre.

| Commit | Fecha | Cambio |
|---|---|---|
| `718a234` | 2026-11-03T10:43:14-06:00 | Initial commit |
| `0795d45` | 2026-11-03T11:07:04-06:00 | chore: prepare isolated Python environment |
| `2a47d73` | 2026-11-03T12:47:56-06:00 | docs: add initial implementation plan and project overview |
| `b952419` | 2026-11-03T12:58:10-06:00 | feat: add initial source catalog |
| `bd81adc` | 2026-11-03T14:00:38-06:00 | feat: add credential loading and configuration tests |
| `1e39563` | 2026-11-03T14:31:01-06:00 | feat: add authenticated HTTP client and metadata checks |
| `f8bcdb5` | 2026-11-03T14:58:39-06:00 | feat: validate source metadata contracts |
| `89303ae` | 2026-11-03T15:29:23-06:00 | feat: plan sample windows from metadata date ranges |
| `4c894c6` | 2026-11-03T16:33:17-06:00 | feat: capture and profile source observation samples |
| `6485538` | 2026-11-03T17:14:43-06:00 | docs: define PostgreSQL model and quality rules |
| `90381bf` | 2026-11-03T18:27:31-06:00 | feat: prepare versioned PostgreSQL schema |
| `57929ee` | 2026-11-03T19:30:16-06:00 | feat: add validated Silver persistence and run tracking |
| `f19cc14` | 2026-11-03T20:22:45-06:00 | feat: validate banking calendar and calculate monthly Gold references |
| `d995cb5` | 2026-11-03T21:15:28-06:00 | feat: publish Silver Gold and watermark atomically |
| `67f149a` | 2026-11-03T22:05:17-06:00 | feat: add explicit historical extraction through Gold |
| `50fa914` | 2026-11-03T22:45:06-06:00 | feat: add independent incremental loading with bounded revisions |
| `7620212` | 2026-11-03T23:13:27-06:00 | docs: documentation improvement |
| `7d3d0b9` | 2026-11-03T23:37:37-06:00 | feat: add run recovery reprocessing and PostgreSQL dashboard |

Se incorporaron los archivos nuevos, la documentación y los recursos de entrega de `VersionNueva`. En el código existente se añadió la lectura opcional del watermark sin bloqueo, conservando comentarios y docstrings originales. Las exclusiones de Git se ampliaron sin retirar las protecciones existentes.

Las evidencias importadas describen las verificaciones realizadas en el entorno de origen. Esta integración no registra tareas de Windows, no consulta las APIs ni ejecuta cargas sobre la base real. Sus comprobaciones locales se registran por separado, sin sustituir los informes originales.

### Comprobaciones locales de esta integración

El 4 de noviembre de 2026 se ejecutó `python -m tests.run` en el entorno del repositorio: 254 casos descubiertos, 163 aprobados y 91 SQL omitidos, sin fallos ni errores. No se habilitó una conexión PostgreSQL de pruebas. Los cinco scripts PowerShell pasaron el análisis de sintaxis y `git diff --check` terminó sin incidencias. Se verificaron los bytes de los 53 archivos nuevos contra el origen, la sintaxis Python y la conservación de comentarios y docstrings en `watermarks.py`.

No se construyó ni se instaló un wheel nuevo en esta integración: el entorno actual no incluye `build`, `setuptools` ni `wheel`. Las evidencias de instalación y scheduler copiadas corresponden al entorno de origen, no acreditan una instalación ni una tarea registrada en este equipo.

### Depuración de documentación para la entrega

Se retiraron dos documentos dedicados al repaso básico de Python y de la salida de pruebas. Se conservaron las guías que explican decisiones de diseño, contratos, precisión, calendarios, publicación y operación. La revisión de los archivos de entrega no encontró referencias a los documentos retirados. Los archivos de código y las evidencias originales permanecen intactos.

### Revisión de coherencia y redacción impersonal

Se revisaron los 23 documentos Markdown conservados. Se unificaron las rutas de ejecución con la raíz del repositorio y las referencias históricas con sus commits. Se separaron las evidencias del entorno de origen de las comprobaciones locales y se unificó la redacción impersonal. Las menciones a peticiones HTTP, cuentas de acceso y sesiones de base de datos conservan su significado técnico.

### Commits de cierre

| Commit | Etapa | Alcance |
|---|---|---|
| `4124ba9` | Documentación técnica pendiente | Guías de cargas, recuperación y dashboard, configuración pública y evidencias de esa etapa. |
| `e404f41` | Empaquetado y automatización | Wheel, ejecutor programado, preflight de estado, scripts Windows y pruebas. |
| Este commit: `docs: finalize project documentation and design deliverables` | Documentación final | Modelo, resultados, operación, evidencias archivadas, justificación del diseño y capturas de la aplicación. |

Antes del cierre se ejecutó nuevamente la suite: 254 casos descubiertos, 163 aprobados y 91 SQL omitidos, sin fallos ni errores. Los recursos de la antigua presentación se retiraron de la entrega y su generador quedó excluido por depender de archivos eliminados.
