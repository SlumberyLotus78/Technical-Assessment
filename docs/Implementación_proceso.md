# Proceso de implementación

## 1. Alcance de la entrega

El proyecto integra precios mensuales de maíz, trigo y soya de FRED con el FIX diario de Banxico para publicar referencias mensuales en pesos mexicanos. Python realiza la extracción, los controles y las transformaciones; PostgreSQL conserva las observaciones y el producto analítico; Streamlit y Plotly permiten consultar los resultados.

El producto real comprende enero de 2009 a septiembre de 2026: **5,102 observaciones Silver, 213 medias FIX y 639 referencias Gold**. La [evidencia de estado](evidencias/entrega_final/estado_real.json) conserva las comprobaciones del producto. El [informe analítico](RESULTADOS_ANALISIS_ES.md) explica el periodo seleccionado y sus resultados.

## 2. Componentes implementados

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

## 3. Flujo de datos y controles

Las consultas obtienen metadatos y observaciones mediante APIs autenticadas. Bronze conserva el JSON y el contexto de extracción antes de validar las observaciones. Cada captura tiene identificador, ruta y SHA-256. Los datos se interpretan con `Decimal`; las reglas comprueban contratos, fechas, valores, duplicados, cobertura y procedencia.

Silver almacena una observación vigente por proveedor, serie y fecha. La cobertura FIX se valida contra calendarios bancarios revisados de 2009 a 2026. Gold calcula la media FIX mensual, las referencias en MXN/t y las variaciones mensuales y anuales por fecha exacta, con 34 dígitos significativos y `ROUND_HALF_EVEN`.

La publicación confirma Silver, Gold, watermark y éxito en una misma transacción. Un bloqueo serializa las publicaciones. Los controles comprueban continuidad temporal, coincidencia con las capturas y conciliación de los cálculos. Un fallo revierte los cambios del producto y conserva el diagnóstico operativo.

El [modelo](MODELO_DATOS_ES.md), el [diccionario](DICCIONARIO_DATOS_ES.md) y las [reglas de calidad](REGLAS_CALIDAD_ES.md) detallan tablas, campos y condiciones de publicación.

## 4. Cargas, recuperación y reproceso

| Operación | Comportamiento |
|---|---|
| Histórico | Recibe un intervalo explícito de meses cerrados, exige ausencia de watermark y publica el producto completo hasta Gold. |
| Incremental | Exige inicialización, consulta meses nuevos y revisa por defecto los tres últimos meses publicados. La revisión se configura entre cero y doce meses. |
| Reproceso | Reconsulta un intervalo dentro del producto publicado, conserva sus límites y recalcula los resultados afectados. |
| Recuperación | Obtiene el bloqueo, comprueba el estado durable y reutiliza capturas completas e íntegras mediante un intento nuevo cuando no existe una publicación posterior incompatible. |

Los comandos comparten reglas y transformaciones. Una revisión puede terminar correctamente sin modificar hechos. Un incremental sin meses seleccionados y con revisión desactivada comprueba el producto y registra `skipped` sin modificar el watermark.

## 5. Dashboard y análisis

El dashboard lee Gold y watermark mediante una transacción `REPEATABLE READ, READ ONLY`. Comprueba las dependencias analíticas antes de mostrar índices base cien, atribución simétrica y comparación entre granos. Las unidades, denominadores y límites nominales se explican en la [metodología](ANALISIS_Y_DASHBOARD_ES.md).

Las [capturas de la aplicación](../Entregables/Capturas) muestran enero de 2009 a septiembre de 2026. El informe analítico utiliza enero de 2010 a septiembre de 2026, conservando 2009 como contexto de los comparadores. Ambas selecciones identifican sus periodos y bases de cálculo.

## 6. Distribución y operación

El paquete wheel incluye el código, el SQL y los calendarios. El entorno de automatización ejecuta el incremental con `python -I -m`, logs exclusivos, propagación del código de salida y límite de 90 minutos. El dashboard utiliza dependencias opcionales separadas del proceso programado.

Las evidencias de [instalación](evidencias/entrega_final/wheel_final_installation.json), [automatización](evidencias/entrega_final/automation.json) y [smoke del scheduler](evidencias/entrega_final/scheduler_smoke.json) documentan sus verificaciones. La tarea diaria está configurada para las 20:00 de Ciudad de México, con sesión iniciada y privilegios limitados. El smoke comprueba el producto en modo de solo lectura; no acredita una carga incremental programada completada.

La operación requiere PostgreSQL y Bronze disponibles. Publicar un año posterior a 2026 exige incorporar y revisar su calendario bancario. El [runbook](RUNBOOK_ES.md) documenta instalación, ejecución, logs, recuperación y mantenimiento.

## 7. Pruebas de la entrega

Se ejecutaron y aprobaron **259 pruebas: 168 sin servidor y 91 de integración PostgreSQL**, sin fallos, errores ni omisiones. El [catálogo de pruebas](CATALOGO_PRUEBAS_ES.md) describe los 32 módulos y enumera sus casos. El [resumen de resultados](evidencias/entrega_final/resumen_pruebas.json) conserva el resultado y el listado de los casos SQL ejecutados. La ejecución completa utiliza la conexión exclusiva `TEST_DATABASE_URL`, bases desechables y respuestas HTTP simuladas. No realiza consultas reales a las APIs ni escrituras en la base del producto.

## 8. Desarrollo registrado por commits

Las referencias siguen el orden del historial de Git e identifican los cambios de implementación, documentación y validación incorporados en cada etapa.

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
| Persistencia y preparación Silver | Registro de intentos, capturas y DQ, verificación de integridad, conversión a tipos comunes y escritura por clave natural. | `57929ee` |
| Calendario y transformaciones Gold | Referencia bancaria 2026, regla DQ-09, dependencias mensuales, media FIX, referencias MXN/t y variaciones. | `f19cc14` |
| Publicación transaccional | Escritura Gold, procedencia Silver, validación global, bloqueo del producto y confirmación conjunta de capas, watermark y éxito. | `d995cb5` |
| Coordinación histórica | Periodo explícito, referencias 2009–2026, consultas anuales, reintentos, perfil consolidado y publicación hasta Gold. Ejecución real confirmada. | `67f149a` |
| Coordinación incremental | Plan según watermark y fuentes, revisión configurable, cierre sin trabajo y reutilización modular de captura y publicación. | `50fa914` |
| Revisión de documentación | Revisión del diccionario, modelo de datos, perfilamiento y reglas de calidad; actualización del proceso de implementación. | `7620212` |
| Recuperación y reproceso | Decisión bajo bloqueo, intento nuevo con originales íntegros y correcciones explícitas dentro del histórico. | `7d3d0b9` |
| Análisis y visualización | Lectura consistente de Gold, métricas decimales, tres gráficos y filtros en Streamlit. | `7d3d0b9` |
| Guías y validación del dashboard | Incorporación de guías de cargas, recuperación y controles, configuración visual de Streamlit y evidencias de validación del dashboard. Las guías se consolidaron posteriormente en el cierre documental. | `4124ba9` |
| Distribución y automatización | Wheel 1.0.0, entorno independiente, preflight de solo lectura, logs y tarea diaria registrada. | `e404f41` |
| Evidencias y entregables | Incorporación de capturas, justificación del diseño, resultados del análisis, runbook y evidencias de pruebas, instalación y automatización. | `5ef9868` |
| Configuración de credenciales cifradas | Incorporación del archivo cifrado de claves API, el comando de configuración mediante contraseña, su documentación y pruebas. | `9eeb761` |
| Cierre documental y validación | Consolidación de guías en la documentación final, catálogo y resumen de las 259 pruebas, actualización de evidencias y ajustes de empaquetado, scripts y pruebas. | `8db0042` |
