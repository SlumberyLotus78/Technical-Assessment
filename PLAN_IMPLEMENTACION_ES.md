# Plan de implementación: BANXICO FIX - FRED. Influencia del tipo de cambio en el precio de los granos

Este documento conserva la propuesta inicial del proyecto. Sus etapas expresan el trabajo previsto, no una lista de pendientes actuales. Lo realizado y sus verificaciones se registran en el [proceso de implementación](docs/Implementación_proceso.md) y la [validación final](docs/VALIDACION_FINAL_ES.md).

## 1. Propósito y objetivo

Este documento presenta una propuesta inicial para organizar el desarrollo del proyecto. Los detalles de las fuentes, las reglas específicas y los parámetros de operación se definirán durante las etapas correspondientes.

El objetivo será integrar precios internacionales de maíz, trigo y soya con el tipo de cambio FIX para analizar su referencia mensual en pesos mexicanos.

La pregunta que orientará el análisis será: 

**¿Cómo influyen el precio internacional y el tipo de cambio en la evolución de las referencias de estos granos en pesos?**

Se buscará expresar los precios en una frecuencia y unidad comunes. La referencia resultante servirá para el análisis, su interpretación deberá considerar los componentes adicionales de una compra real, como transporte y condiciones comerciales.

## 2. Alcance previsto

- Consultar dos fuentes mediante sus APIs: FRED para precios de granos y Banxico para el FIX.
- Desarrollar en Python los procesos de extracción, validación y transformación.
- Conservar los datos originales y preparar registros consistentes para su almacenamiento.
- Almacenar observaciones y resultados analíticos en PostgreSQL.
- Implementar primero una carga histórica y después una actualización incremental independiente.
- Construir dos o tres visualizaciones conectadas a la base de datos.
- Preparar la automatización del incremental mediante un paquete instalable.
- Documentar la ejecución, las decisiones y los resultados que se obtengan.

El periodo de análisis se definirá al revisar la disponibilidad y compatibilidad de las fuentes.

## 3. Propuesta técnica y organización

Se propone utilizar Python para la integración, PostgreSQL para la persistencia y Streamlit con Plotly para la consulta visual. Las dependencias y sus versiones se documentarán al preparar cada componente.

El código se organizará por responsabilidad, utilizando funciones con nombres descriptivos. Las reglas de calidad tendrán módulos propios y serán invocadas desde los procesos que las necesiten. Las transformaciones compartidas tendrán una implementación reutilizable.

La estructura general propuesta será:

```text
grain_pipeline/
    common/             Configuración y funciones compartidas
    sources/            Identificación y contratos de las fuentes
    clients/            Comunicación con las APIs
    extraction/         Captura y conservación de originales
    quality/            Reglas de calidad de datos
    transformations/    Preparación y cálculos analíticos
    persistence/        Almacenamiento y control operativo
    orchestration/      Coordinación de cargas y etapas
app/                    Visualización
scripts/                Comandos auxiliares y automatización
tests/                  Pruebas
docs/                   Documentación y notas
```

Las carpetas se incorporarán conforme se implemente cada responsabilidad. Las abstracciones adicionales se introducirán cuando resuelvan una necesidad concreta y mantengan el código comprensible.

## 4. Capas de datos

| Capa | Propósito |
|---|---|
| Bronze | Conservar las respuestas originales y la información necesaria para identificar su origen. |
| Silver | Preparar observaciones con tipos, fechas, unidades y claves consistentes, aplicando reglas de calidad. |
| Gold | Integrar las fuentes en una frecuencia común y producir referencias, variaciones e indicadores para el análisis. |

Los controles operativos permitirán relacionar cada ejecución con sus entradas, su resultado y el avance de la carga.

## 5. Cargas y automatización

### Carga histórica

Se ejecutará de forma explícita para un periodo definido con el objetivo de inspeccionar los datos, evaluar su calidad y establecer la carga inicial hasta Gold. Su publicación satisfactoria establecerá el estado desde el que podrá continuar el incremental.

### Carga incremental

Tendrá un proceso y un comando independientes, utilizando el estado de carga para determinar qué información consultar y actualizar. Requerirá una carga inicial completa y recorrerá las transformaciones necesarias hasta Gold.

Ambas cargas compartirán las reglas de calidad y las transformaciones. Se contemplarán mecanismos para tratar datos repetidos, revisiones de origen e interrupciones, conservando la trazabilidad.

### Control y ejecución programada

Se utilizarán logs para registrar las ejecuciones, incluidos sus errores, y watermarks para conservar el avance. Los watermarks avanzarán únicamente cuando la publicación correspondiente se complete correctamente.

La ejecución programada invocará el incremental mediante un paquete Python distribuible como wheel. La preparación histórica será una operación separada. El mecanismo y la frecuencia de programación se definirán al preparar la automatización.

## 6. Etapas de trabajo

| Etapa | Trabajo previsto | Entregable esperado |
|---|---|---|
| 1. Definición | Precisar la pregunta, el alcance y las fuentes candidatas. | README y plan inicial. |
| 2. Entorno | Preparar Python, dependencias, configuración privada y organización del código. | Entorno reproducible y estructura inicial. |
| 3. Exploración de fuentes | Revisar documentación, autenticación, metadatos y muestras. | Contratos de entrada y notas de exploración. |
| 4. Modelo y calidad | Definir las claves, el almacenamiento, los controles y las validaciones. | Modelo de datos y reglas DQ modulares. |
| 5. Histórico y transformación | Extraer el periodo inicial, perfilarlo y preparar las capas hasta Gold. | Carga histórica comprobada y perfil inicial. |
| 6. Incremental y recuperación | Implementar la actualización por estado y comprobar reejecuciones e interrupciones. | Proceso incremental independiente y verificable. |
| 7. Análisis | Preparar indicadores, visualizaciones e interpretación. | Dashboard conectado a PostgreSQL. |
| 8. Automatización | Empaquetar el código y programar la actualización. | Wheel y ejecución incremental programada. |
| 9. Validación y entrega | Comprobar el conjunto y documentar su reproducción. | Pruebas y documentación. |

Cada etapa incluirá una comprobación apropiada antes de continuar con los componentes que dependan de ella.

## 7. Criterios generales de aceptación

- Las dos fuentes podrán consultarse con autenticación y manejo de errores.
- Las credenciales se mantendrán en configuración privada y fuera del repositorio.
- Las validaciones cubrirán tipos, fechas, valores ausentes, duplicados y cobertura temporal.
- Las fuentes podrán relacionarse mediante claves y periodos claramente definidos.
- La repetición de una carga conservará la consistencia de los datos y evitará duplicaciones.
- El histórico y el incremental podrán ejecutarse por separado, utilizando las mismas transformaciones hasta Gold.
- Los logs y watermarks permitirán conocer el resultado y el avance de las ejecuciones.
- Las visualizaciones consultarán la base de datos y explicarán unidades, periodos y alcance de los indicadores.
- El paquete y las instrucciones permitirán reproducir la operación en un entorno preparado.
- Las pruebas distinguirán los casos simulados de las comprobaciones realizadas con APIs y PostgreSQL.

## 8. Documentación y seguimiento

Se mantendrán instrucciones de preparación y ejecución, un diccionario de datos y notas de las decisiones técnicas. La entrega incluirá evidencias y hallazgos sustentados en los datos para apoyar la explicación técnica del proyecto.

El trabajo avanzará mediante commits asociados a cambios comprensibles y comprobados. Las decisiones concretas, las mediciones y las evidencias se registrarán en notas de implementación y reportes de validación conforme se produzcan.

El README declarará el apoyo de herramientas de IA y reconocerá las fuentes utilizadas.
