# Plan de implementación: BANXICO FIX - FRED. Influencia del tipo de cambio en el precio de los granos

Este documento describe el alcance, la organización y los criterios de aceptación de la entrega. Los componentes implementados se detallan en el [proceso de implementación](docs/Implementación_proceso.md).

## 1. Propósito y objetivo

Las fuentes, las reglas de calidad y los parámetros de operación se documentan en el modelo de datos, el catálogo DQ y el runbook.

El objetivo es integrar precios internacionales de maíz, trigo y soya con el tipo de cambio FIX para analizar su referencia mensual en pesos mexicanos.

La pregunta que orienta el análisis es:

**¿Cómo influyen el precio internacional y el tipo de cambio en la evolución de las referencias de estos granos en pesos?**

Se expresan los precios en una frecuencia y unidad comunes. La referencia resultante sirve para el análisis, su interpretación considera los componentes adicionales de una compra real, como transporte y condiciones comerciales.

## 2. Alcance de la entrega

- Consultar dos fuentes mediante sus APIs: FRED para precios de granos y Banxico para el FIX.
- Desarrollar en Python los procesos de extracción, validación y transformación.
- Conservar los datos originales y preparar registros consistentes para su almacenamiento.
- Almacenar observaciones y resultados analíticos en PostgreSQL.
- Ejecutar el histórico y el incremental mediante comandos independientes.
- Construir tres visualizaciones conectadas a la base de datos.
- Preparar la automatización del incremental mediante un paquete instalable.
- Documentar la ejecución, las decisiones y los resultados obtenidos.

El producto comprende 2009-01 a 2026-09; el informe analítico compara 2010-01 a 2026-09.

## 3. Solución técnica y organización

Se utiliza Python para la integración, PostgreSQL para la persistencia y Streamlit con Plotly para la consulta visual. Las dependencias se declaran en `requirements.txt` y `pyproject.toml`.

El código se organiza por responsabilidad, utilizando funciones con nombres descriptivos. Las reglas de calidad tienen módulos propios y son invocadas desde los procesos que las necesiten. Las transformaciones compartidas tienen una implementación reutilizable.

La estructura del proyecto es:

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

Cada paquete concentra una responsabilidad y utiliza las funciones compartidas de configuración, fechas y precisión decimal.

## 4. Capas de datos

| Capa | Propósito |
|---|---|
| Bronze | Conservar las respuestas originales y la información necesaria para identificar su origen. |
| Silver | Preparar observaciones con tipos, fechas, unidades y claves consistentes, aplicando reglas de calidad. |
| Gold | Integrar las fuentes en una frecuencia común y producir referencias, variaciones e indicadores para el análisis. |

Los controles operativos permiten relacionar cada ejecución con sus entradas, su resultado y el avance de la carga.

## 5. Cargas y automatización

### Carga histórica

Se ejecuta de forma explícita para un periodo definido con el objetivo de inspeccionar los datos, evaluar su calidad y establecer la carga inicial hasta Gold. Su publicación satisfactoria establece el estado desde el que continúa el incremental.

### Carga incremental

Tiene un proceso y un comando independientes, utilizando el estado de carga para determinar qué información consultar y actualizar. Requiere una carga inicial completa y recorre las transformaciones necesarias hasta Gold.

Ambas cargas comparten las reglas de calidad y las transformaciones. Se incluyen mecanismos para tratar datos repetidos, revisiones de origen e interrupciones, conservando la trazabilidad.

### Control y ejecución programada

Se utilizan logs para registrar las ejecuciones, incluidos sus errores, y watermarks para conservar el avance. Los watermarks avanzan únicamente cuando la publicación correspondiente se completa correctamente.

La ejecución programada invoca el incremental mediante un paquete Python distribuible como wheel. La preparación histórica es una operación separada. El Programador de tareas de Windows configura una ejecución diaria a las 20:00 de Ciudad de México.

## 6. Organización del trabajo

| Etapa | Trabajo | Entregable |
|---|---|---|
| 1. Definición | Precisar la pregunta, el alcance y las fuentes candidatas. | README y plan de implementación. |
| 2. Entorno | Preparar Python, dependencias, configuración privada y organización del código. | Entorno reproducible y estructura inicial. |
| 3. Exploración de fuentes | Revisar documentación, autenticación, metadatos y muestras. | Contratos de entrada y notas de exploración. |
| 4. Modelo y calidad | Definir las claves, el almacenamiento, los controles y las validaciones. | Modelo de datos y reglas DQ modulares. |
| 5. Histórico y transformación | Extraer el periodo inicial, perfilarlo y preparar las capas hasta Gold. | Carga histórica comprobada y perfil inicial. |
| 6. Incremental y recuperación | Implementar la actualización por estado y comprobar reejecuciones e interrupciones. | Proceso incremental independiente y verificable. |
| 7. Análisis | Preparar indicadores, visualizaciones e interpretación. | Dashboard conectado a PostgreSQL. |
| 8. Automatización | Empaquetar el código y programar la actualización. | Wheel y ejecución incremental programada. |
| 9. Validación y entrega | Comprobar el conjunto y documentar su reproducción. | Pruebas y documentación. |

Las verificaciones de la entrega se describen en el [catálogo de pruebas](docs/CATALOGO_PRUEBAS_ES.md).

## 7. Criterios generales de aceptación

- Las dos fuentes se consultan con autenticación y manejo de errores.
- Las credenciales se mantienen en configuración privada y fuera del repositorio.
- Las validaciones cubren tipos, fechas, valores ausentes, duplicados y cobertura temporal.
- Las fuentes se relacionan mediante claves y periodos claramente definidos.
- La repetición de una carga conserva la consistencia de los datos y evita duplicaciones.
- El histórico y el incremental se ejecutan por separado, utilizando las mismas transformaciones hasta Gold.
- Los logs y watermarks permiten conocer el resultado y el avance de las ejecuciones.
- Las visualizaciones consultan la base de datos y explican unidades, periodos y alcance de los indicadores.
- El paquete y las instrucciones permiten reproducir la operación en un entorno preparado.
- Las pruebas distinguen los casos simulados de las comprobaciones realizadas con APIs y PostgreSQL.

## 8. Documentación y seguimiento

La entrega incluye instrucciones de preparación y ejecución, modelo de datos, diccionario, reglas de calidad, catálogo de pruebas, evidencias y resultados analíticos. La [justificación del diseño](Entregables/Justificacion_dise%C3%B1o.md) explica las decisiones técnicas y reúne las capturas del dashboard.

El [proceso de implementación](docs/Implementación_proceso.md) relaciona los componentes con sus commits. El README reconoce las fuentes y el apoyo de herramientas de IA.
