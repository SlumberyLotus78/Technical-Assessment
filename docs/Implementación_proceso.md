# Proceso de implementación

**Corte del documento:** 3 de noviembre de 2026 4:00 pm.

## 1. Objetivo y estado del proyecto

El proyecto integra precios internacionales de maíz, trigo y soya de FRED con el tipo de cambio FIX de Banxico para preparar referencias mensuales en pesos mexicanos. El alcance y las etapas previstas se mantienen en el [plan de implementación](../PLAN_IMPLEMENTACION_ES.md).

Se completó la preparación del entorno, la conexión autenticada a las fuentes, la validación de sus metadatos y la extracción de una muestra con conservación de respuestas y perfil de calidad. La muestra contiene 30 observaciones y completó las reglas implementadas sin incidencias. La cobertura diaria de FIX permanece pendiente de validación con el calendario bancario.

Sobre esa evidencia se definieron el modelo de persistencia, el diccionario de campos y el catálogo de reglas para las cargas. El diseño incluye la procedencia de observaciones, los agregados y referencias mensuales, el registro de intentos y el avance publicado hasta Gold. Su materialización en PostgreSQL corresponde al siguiente entregable.


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
| Modelo y calidad | Diseño de ocho entidades, diccionario de campos y reglas de publicación para histórico e incremental independientes. | Avance documental actual, pendiente de commit. |

## 3. Organización de la implementación

El código se distribuye por responsabilidad mediante funciones y paquetes, donde las reglas de calidad se mantienen separadas del transporte y de la coordinación de la extracción.

| Componente | Responsabilidad implementada |
|---|---|
| `common/` | Configuración privada, interpretación de fechas y operaciones de calendario compartidas. |
| `clients/` | Comunicación HTTP, autenticación, tiempos de espera y errores controlados. |
| `sources/` | Catálogo, contratos de metadatos y observaciones, consultas y selección de ventanas. |
| `extraction/` | Conservación de capturas y coordinación de la muestra. |
| `quality/` | Interpretación decimal y perfil de calidad reutilizable. |
| `tests/` | Casos simulados de configuración, comunicación, contratos, fechas, captura y calidad. |

El flujo implementado consulta los metadatos, determina las ventanas, solicita las observaciones, conserva el JSON recibido y aplica el contrato y las reglas de perfil. Los números se interpretan directamente desde texto con `Decimal`, manteniendo la precisión disponible en las fuentes.

El [modelo de datos](MODELO_DATOS_ES.md), el [diccionario](DICCIONARIO_DATOS_ES.md) y el [catálogo DQ](REGLAS_CALIDAD_ES.md) especifican las responsabilidades de persistencia y transformación que se incorporarán a estos paquetes. Los documentos distinguen las reglas de exploración ya ejecutadas de las garantías de carga y publicación pendientes.

## 4. Captura y trazabilidad

Cada diagnóstico crea una carpeta independiente en `data/bronze/samples/`. Una ejecución completa conserva cuatro registros de metadatos, cuatro respuestas de observaciones y un perfil consolidado. Las capturas incluyen proveedor, código de serie, instante UTC y ventana de consulta.

Las respuestas de observaciones se guardan antes de comprobar su contrato, si una consulta o una estructura fallan entonces las capturas previas permanecen y la ejecución no genera el perfil final. 

Los archivos existentes se preservan mediante creación exclusiva.

La ejecución inicial examinada es `20261103T215513253606Z_f3eb3f86a0734026aa8761a7d23324f7`, con fecha de referencia 2026-11-03 y mes final de muestra 2026-09. Sus nueve archivos se conservaron en [evidencias de perfilamiento inicial](evidencias/perfilamiento_inicial/manifest.json). El manifiesto identifica la ejecución, las verificaciones y las sumas SHA-256 de cada archivo.

Las capturas operativas permanecen excluidas de Git. La copia seleccionada para documentar el perfil inicial se conserva dentro de `docs/evidencias/` y acompaña al informe.

## 5. Verificaciones y resultados

| Tipo de verificación | Evidencia disponible |
|---|---|
| Pruebas simuladas | 63 casos aprobados en la comprobación local del avance de extracción y perfil. |
| Consultas reales previas | Confirmación de acceso, contratos de metadatos, disponibilidad y propuesta de ventanas de las cuatro series. |
| Muestra real | 3 observaciones por grano de julio a septiembre de 2026 y 21 observaciones FIX de septiembre: 30 registros en total. |
| Reproducción del perfil | Los cuatro perfiles recalculados desde las capturas coinciden con `profile.json`. |
| Calidad observada | Cero ausentes, formatos inválidos, valores no positivos, fechas incompatibles, fechas fuera de ventana y duplicados. |
| Cobertura mensual | Tres meses esperados y tres meses con valores utilizables en cada grano. |
| Cobertura diaria | Pendiente del calendario hábil bancario; el conteo de 21 registros no acredita por sí solo la integridad del mes FIX. |
| Revisión de diseño | Definición de claves, tipos, relaciones, procedencia, reglas DQ y límite transaccional de la futura publicación. La comprobación del avance documental incluye enlaces y consistencia con la evidencia. |

Las pruebas simuladas verifican el comportamiento del código mientras que la muestra real aporta evidencia sobre los registros efectivamente recibidos. Ambas verificaciones tienen alcances distintos y se documentan por separado.

## 6. Estado de las capas y cargas

| Frente | Estado al corte |
|---|---|
| Bronze | Captura local de muestras implementada y comprobada con respuestas reales. |
| Silver | Modelo definido: catálogo y una observación vigente por proveedor, serie y fecha. Persistencia pendiente. |
| Gold | Definidas la media FIX certificada, las referencias MXN/t y las variaciones mensual y anual. Transformaciones pendientes. |
| Carga histórica | Contrato de inicialización y publicación definido; periodo y proceso pendientes. |
| Carga incremental | Contrato independiente definido, con requisito de histórico inicializado y revisión de periodos anteriores. Implementación pendiente. |
| Persistencia y control | Definidos registros de ejecuciones, capturas, DQ y watermark común al producto. SQL y conexión pendientes en esta rama. |
| Visualización y automatización | Pendientes del modelo analítico, el paquete instalable y la programación del incremental. |

La extracción de muestra es un diagnóstico de fuentes. Su terminación acredita ese recorrido y sus reglas actuales y la publicación de datos y el avance de watermarks corresponden a las futuras cargas.

## 7. Continuidad prevista

El siguiente entregable será la creación SQL de esquemas, tablas y restricciones, seguida de la configuración y comprobación de conexión. La cobertura FIX requerirá después el calendario bancario y el perfil del periodo completo seleccionado antes de publicar un agregado.

La carga histórica establecerá la base inicial hasta Gold y las cargas incrementales se implementará después como proceso independiente, compartiendo reglas y transformaciones, con control de reejecuciones y actualización de watermarks tras una publicación satisfactoria. La visualización y el empaquetado para automatización se incorporarán sobre esa base.

Esta bitácora se actualizará con cada avance, su referencia de commit, la evidencia obtenida y los pendientes que afecten a las etapas posteriores.
