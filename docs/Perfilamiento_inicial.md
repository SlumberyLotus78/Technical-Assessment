# Perfilamiento inicial de las fuentes

**Fecha de referencia:** 2026-11-03.

**Mes final de la muestra:** septiembre de 2026.

**Ámbito:** muestra real del proyecto.

Este informe conserva los resultados del diagnóstico inicial. La certificación bancaria posterior y la validación del histórico completo se documentan al final, no sustituyen ni reescriben el perfil original.

## 1. Resultado principal

La muestra analizada contiene **30 observaciones: nueve precios mensuales de granos y 21 registros diarios FIX**. Los 30 valores son numéricos y positivos. Las reglas aplicadas no detectaron ausentes, formatos inválidos, fechas incompatibles, registros fuera de ventana ni fechas duplicadas.

Las tres series de granos tienen los tres meses esperados. En el perfil inicial, la cobertura diaria de FIX quedó pendiente del calendario hábil bancario, tal como registra `coverage_status: pending_banking_calendar`. El resultado favorable de sus controles describe los registros recibidos y conserva esa comprobación pendiente. [Perfil generado](evidencias/perfilamiento_inicial/profile.json).

## 2. Procedencia y comprobación de la evidencia

| Elemento | Identificación |
|---|---|
| Ejecución | `20261103T215523120075Z_7bb854f46f16499eb08a3e2a98098072` |
| Ubicación operativa | `data/bronze/samples/20261103T215523120075Z_7bb854f46f16499eb08a3e2a98098072/` |
| Momento de las capturas | 2026-11-03, entre 21:55:23 y 21:55:26 UTC. |
| Estado registrado | `status: completed`, `has_issues: false`. |
| Archivos examinados | Cuatro capturas de metadatos, cuatro capturas de observaciones y un perfil consolidado. |
| Evidencia conservada | Copias de los nueve archivos en `docs/evidencias/perfilamiento_inicial/`. |

Para preparar este informe se comprobaron los contratos de los cuatro registros de metadatos y de las cuatro respuestas de observaciones. Los perfiles se recalcularon desde las capturas utilizando las funciones implementadas y coincidieron con los cuatro resultados almacenados en `profile.json`. Esta revisión utilizó los archivos de la ejecución identificada, sin volver a consultar las APIs.

El [manifiesto de evidencia](evidencias/perfilamiento_inicial/manifest.json) conserva la procedencia, el resultado de la reproducción y el tamaño y SHA-256 de cada archivo. Las copias mantienen los mismos bytes que los archivos operativos examinados. Dentro de las capturas, `payload` contiene el JSON interpretado por el cliente, con su contexto de origen.

## 3. Disponibilidad declarada y selección de la muestra

| Fuente y serie | Frecuencia declarada | Unidad | Inicio declarado | Fin declarado |
|---|---|---|---|---|
| FRED · Maíz · `PMAIZMTUSDM` | Mensual | USD por tonelada métrica | 1992-01-01 | 2026-09-01 |
| FRED · Trigo · `PWHEAMTUSDM` | Mensual | USD por tonelada métrica | 1992-01-01 | 2026-09-01 |
| FRED · Soya · `PSOYBUSDM` | Mensual | USD por tonelada métrica | 1992-01-01 | 2026-09-01 |
| Banxico · FIX · `SF43718` | Diaria | MXN por USD | 1991-11-12 | 2026-11-03 |

Los campos se contrastaron con el catálogo. En FRED se comprobaron también la identificación, el título y la clasificación `NSA`, en Banxico, la identificación, el componente de determinación FIX y la clasificación `Tipo de Cambio`. Fuentes: capturas de metadatos de [maíz](evidencias/perfilamiento_inicial/fred_PMAIZMTUSDM_metadata.json), [trigo](evidencias/perfilamiento_inicial/fred_PWHEAMTUSDM_metadata.json), [soya](evidencias/perfilamiento_inicial/fred_PSOYBUSDM_metadata.json) y [FIX](evidencias/perfilamiento_inicial/banxico_SF43718_metadata.json).

Con fecha de referencia 2026-11-03, octubre era el último mes calendario cerrado. Las tres series FRED declararon septiembre como último periodo disponible, por lo que septiembre delimitó la muestra común. Se consultaron julio–septiembre para los granos y septiembre para FIX, conforme al tamaño de muestra implementado.

Los límites de metadatos describen la disponibilidad declarada, esta muestra no evalúa la continuidad de todo el histórico. Esa comprobación corresponde a la extracción, el perfilamiento y la publicación del periodo completo.

## 4. Volumen y cobertura observados

| Serie | Ventana consultada | Registros | Valores numéricos | Primera fecha recibida | Última fecha recibida | Cobertura evaluada |
|---|---|---:|---:|---|---|---|
| Maíz | 2026-07-01 a 2026-09-30 | 3 | 3 | 2026-07-01 | 2026-09-01 | 3 de 3 meses con valor utilizable. |
| Trigo | 2026-07-01 a 2026-09-30 | 3 | 3 | 2026-07-01 | 2026-09-01 | 3 de 3 meses con valor utilizable. |
| Soya | 2026-07-01 a 2026-09-30 | 3 | 3 | 2026-07-01 | 2026-09-01 | 3 de 3 meses con valor utilizable. |
| FIX | 2026-09-01 a 2026-09-30 | 21 | 21 | 2026-09-01 | 2026-09-30 | 21 fechas distintas, calendario bancario pendiente. |
| **Total** | Ventanas de la muestra | **30** | **30** | — | — | Frecuencias evaluadas por separado. |

En las series mensuales, `2026-09-01` identifica el periodo de septiembre. Que la última fecha recibida sea el día uno y la ventana termine el día treinta es coherente con esta representación. `expected_months` es tres y `missing_months` está vacío en los tres perfiles. [Resultados por serie](evidencias/perfilamiento_inicial/profile.json).

Para FRED también se verificó que `count` fuera tres, `offset` cero y la lista recibida tuviera tres registros, con `units: lin` y `output_type: 1`. Esto confirma la integridad de la página recibida bajo el contrato aplicado. Las respuestas de [maíz](evidencias/perfilamiento_inicial/fred_PMAIZMTUSDM_observations.json), [trigo](evidencias/perfilamiento_inicial/fred_PWHEAMTUSDM_observations.json) y [soya](evidencias/perfilamiento_inicial/fred_PSOYBUSDM_observations.json) conservan esos controles.

Los 21 registros FIX llegan dentro de septiembre y no repiten fecha. El perfil no establece todavía cuántas publicaciones correspondían al calendario bancario. Por eso el inicio y fin observados y la ausencia de duplicados no bastan para certificar la cobertura diaria completa. [Respuesta FIX](evidencias/perfilamiento_inicial/banxico_SF43718_observations.json).

## 5. Resultados de calidad

| Control del perfil | Maíz | Trigo | Soya | FIX | Interpretación |
|---|---:|---:|---:|---:|---|
| Valores ausentes | 0 | 0 | 0 | 0 | Todos los registros contienen un valor interpretable. |
| Valores con formato inválido | 0 | 0 | 0 | 0 | Los textos cumplen las reglas numéricas aplicadas. |
| Valores menores o iguales a cero | 0 | 0 | 0 | 0 | Los 30 valores numéricos son positivos. |
| Fechas inválidas | 0 | 0 | 0 | 0 | Todas las fechas cumplen su formato y existen en el calendario. |
| Fechas fuera de ventana | 0 | 0 | 0 | 0 | Todas las observaciones pertenecen al intervalo solicitado. |
| Fechas mensuales distintas del primer día | 0 | 0 | 0 | No aplica | Los nueve precios identifican correctamente su mes. |
| Apariciones adicionales de una fecha | 0 | 0 | 0 | 0 | No se detectaron duplicados de fecha por serie. |
| Meses sin valor utilizable | 0 | 0 | 0 | No aplica | Los tres periodos mensuales están presentes en cada grano. |

La evidencia de estos controles es el [perfil consolidado](evidencias/perfilamiento_inicial/profile.json). El campo `non_month_start_dates` se almacena como cero también en FIX, pero la regla solo se aplica a frecuencia mensual, aquí se representa como «No aplica». Lo mismo ocurre con la comprobación mensual de cobertura, cuyo `expected_months` es `null` para FIX.

Los contadores son independientes: una observación podría acumular varios problemas. En esta muestra todos son cero y las cuatro listas recibidas tienen registros. Por ello `has_issues` es falso tanto por serie como en el consolidado. Las funciones de perfil describen los datos y no los corrigen ni completan.

## 6. Rangos numéricos y precisión

| Serie | Unidad | Mínimo observado | Fecha del mínimo | Máximo observado | Fecha del máximo |
|---|---|---:|---|---:|---|
| Maíz | USD/t | 213.1901539821428 | 2026-07-01 | 236.9161241071429 | 2026-09-01 |
| Trigo | USD/t | 228.73884495 | 2026-07-01 | 246.85180245 | 2026-09-01 |
| Soya | USD/t | 442.4505721529122 | 2026-07-01 | 481.7223363582059 | 2026-09-01 |
| FIX | MXN/USD | 16.8748 | 2026-09-04 | 18.0710 | 2026-09-29 |

Los extremos coinciden con `value_min` y `value_max` del perfil. Sus fechas se obtuvieron de los registros de las cuatro capturas de observaciones vinculadas arriba. Se conservan todos los decimales recibidos, incluido el cero final de `18.0710`.

Los valores FRED de esta muestra llegan hasta 13 posiciones decimales en cada serie, los de FIX tienen cuatro. Esta diferencia sustenta la conservación de precisión decimal en el almacenamiento y el tratamiento de cada unidad por separado. Los rangos describen únicamente los periodos consultados y no constituyen límites de aceptación para todo el histórico.

## 7. Límites del diagnóstico y comprobaciones posteriores

Los resultados acreditan que las cuatro fuentes entregaron observaciones con estructura compatible y que la muestra pasó los controles iniciales. Sustentan continuar con el modelo de datos, conservando proveedor, serie, fecha, unidad, valor decimal y referencia de captura, junto con controles de unicidad por serie y fecha.

El diagnóstico inicial tenía tres límites de alcance:

- **Cobertura FIX:** no contrastaba el conjunto de fechas con el calendario hábil bancario para acreditar un mes completo.
- **Alcance temporal:** el histórico fuera de julio–septiembre de 2026 todavía no fue perfilado en este avance, el FIX de la muestra solo corresponde a septiembre.
- **Integración analítica:** no incluía FIX de julio y agosto ni producía referencias Gold en pesos, conservaba las unidades originales.

Posteriormente, la [vista previa Gold](evidencias/calendario_gold/vista_previa.json) certificó las 21 fechas FIX de septiembre de 2026 y calculó tres referencias en memoria desde estas mismas capturas. La carga histórica incorporó las cuatro series para 2009-01 a 2026-09, con cobertura bancaria mensual. Se confirmó su ejecución real y el preflight instalado verificó después 5,102 observaciones Silver, 213 medias FIX y 639 referencias Gold mediante lecturas y comprobación de originales. La [validación final](VALIDACION_FINAL_ES.md) y el [proceso de implementación](Implementación_proceso.md) registran esas verificaciones con sus alcances propios, las 30 observaciones iniciales siguen siendo únicamente la muestra aquí examinada.
