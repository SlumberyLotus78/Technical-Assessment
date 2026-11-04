# Guía de lectura: contratos de entrada de metadatos

## 1. Qué significa contrato en este proyecto

Un contrato de entrada es el conjunto de condiciones que una respuesta debe satisfacer para que podamos utilizarla con el significado esperado. Recibir HTTP 200 y JSON permite comprobar la comunicación, también necesitamos comprobar qué describe ese JSON.

En esta etapa exigimos la estructura e identidad de cada serie, su título y los campos de unidad, frecuencia y clasificación definidos en el catálogo.

## 2. La separación de responsabilidades

| Archivo | Responsabilidad |
|---|---|
| `sources/catalog.py` | Declara los títulos y valores esperados. |
| `clients/http.py` | Envía la petición y comprueba HTTP y JSON. |
| `sources/contracts.py` | Interpreta la estructura y aplica las reglas de metadatos. |
| `sources/metadata.py` | Coordina la consulta y llama al contrato. |

`fetch_metadata` conserva su interfaz y devuelve el registro aceptado. La comprobación de estructura e identidad que antes estaba dentro de esa función se trasladó a `read_series_record`, junto a las nuevas reglas del contrato.

## 3. Qué esperamos de cada fuente

| Propiedad | FRED, para los tres granos | Banxico, para FIX |
|---|---|---|
| Identificador | Campo `id` con el código del catálogo | Campo `idSerie` con `SF43718` |
| Título | Campo `title` con el título esperado | Campo `titulo` que contenga la fecha de determinación FIX |
| Unidad | `units`: `U.S. Dollars per Metric Ton` | `unidad`: `Pesos por Dólar` |
| Frecuencia | `frequency`: `Monthly`, y `frequency_short`: `M` | `periodicidad`: `Diaria` |
| Clasificación | `seasonal_adjustment_short`: `NSA` | `cifra`: `Tipo de Cambio` |
| Rango declarado | `observation_start` y `observation_end`, en ISO | `fechaInicio` y `fechaFin`, en DD/MM/YYYY |

Las fichas de [maíz](https://fred.stlouisfed.org/series/PMAIZMTUSDM), [trigo](https://fred.stlouisfed.org/series/PWHEAMTUSDM) y [soya](https://fred.stlouisfed.org/series/PSOYBUSDM) describen las unidades, la frecuencia y la ausencia de ajuste estacional. El [cuadro de Banxico](https://www.banxico.org.mx/SieInternet/consultarDirectorioInternetAction.do?accion=consultarCuadro&idCuadro=CF102&locale=es) identifica las propiedades del FIX. Las estructuras de consulta corresponden a los contratos de [FRED](https://fred.stlouisfed.org/docs/api/fred/series.html) y [Banxico](https://www.banxico.org.mx/SieAPIRest/service/v1/doc/consultaSeries).

`unit` y `frequency` siguen siendo las etiquetas internas del catálogo, como `USD/t` y `monthly`. El nuevo diccionario `expected_metadata` contiene los nombres y valores que esperamos recibir del proveedor.

Las tres entradas FRED comparten `FRED_GRAIN_METADATA`. Esta definición se utiliza para lectura, los datos ficticios de cada prueba se construyen como diccionarios independientes.

## 4. Cómo leer las funciones

### normalize_text

Recibe un valor y, si es texto, combina los espacios con `split` y `join` y aplica `casefold` para comparar mayúsculas. Por ejemplo, `"  Monthly  "` y `"MONTHLY"` producen el mismo texto de comparación.

La función prepara texto para comparar. El registro recibido conserva sus valores originales. Una unidad distinta seguirá siendo incompatible: cambiar espacios no transforma bushels en toneladas.

### read_series_record

Comprueba que la raíz sea un diccionario y que no declare un error. Obtiene la lista de registros según el proveedor, exige un único registro y comprueba su identificador.

### validate_metadata

Llama a `read_series_record` y delega la validación del registro en `validate_metadata_record`. Si todas las reglas se cumplen, devuelve el registro original.

### validate_metadata_record

Recibe directamente el registro nativo, comprueba su identidad, recorre los campos esperados del catálogo y valida el título y las fechas de disponibilidad. Si se incumple una regla, lanza `ValueError` indicando el campo. Esta función se comparte entre la consulta API y la revalidación de los metadatos archivados en Bronze.

En FRED se compara el título completo normalizado. En Banxico se busca el componente esperado dentro del título jerárquico. Así distinguimos el FIX de determinación de otras series de tipo de cambio.

### read_metadata_range

Interpreta los campos de cada proveedor usando `common/dates.py`, exige inicio anterior o igual a fin y comprueba los identificadores de periodo de las series mensuales. `validate_metadata_record` la invoca como parte del contrato, también cuando se llega desde `validate_metadata`.

## 5. Por qué actualizamos los datos de prueba

Los primeros escenarios de `test_metadata.py` solo necesitaban identificador y título. Ahora el mismo flujo exige también las propiedades del contrato.

`tests/fixtures.py` construye registros ficticios completos y los envuelve en la estructura de cada proveedor. Así compartimos la preparación entre las pruebas de coordinación y las del contrato. Estos datos sirven para comprobar las reglas, su construcción a partir del catálogo no constituye una consulta real.

La primera etapa añadió ocho métodos: aceptación de las cuatro series, normalización que conserva originales, unidades incorrectas, frecuencias incorrectas, títulos incorrectos, campos ausentes, tipos inesperados y clasificación incompatible. La ampliación temporal suma otros cuatro a este archivo y añade pruebas de calendario y muestra en módulos propios, alcanzando cuarenta casos. La [guía de fechas](GUIA_FECHAS_Y_MUESTRA_ES.md) explica ese avance. La [descarga y perfil de observaciones](GUIA_MUESTRA_Y_PERFIL_ES.md) amplió la suite a 63 casos. La etapa posterior de [PostgreSQL](GUIA_POSTGRESQL_ES.md) documenta el total vigente y las condiciones de integración.

## 6. Comandos de comprobación

Desde la raí del repositorio, con el entorno activado:

```powershell
python -X utf8 -m unittest discover -s tests -v
```

Los casos de esta guía utilizan escenarios simulados. Los recuentos de la sección anterior corresponden a sus etapas de desarrollo, el total del cierre se conserva en la [validación final](VALIDACION_FINAL_ES.md). La [guía PostgreSQL](GUIA_POSTGRESQL_ES.md) explica las condiciones de integración. `unittest` no carga `.env`: sin `TEST_DATABASE_URL` en el entorno, los casos de servidor se omiten y se informa su cantidad.

Después se vuelve a consultar la fuente real con la configuración privada:

```powershell
python -X utf8 -m grain_pipeline.sources.metadata --env-file .env
```

La versión actual muestra `metadatos comprobados`, el rango declarado y las ventanas propuestas. La clasificación también se comprueba mediante los campos del catálogo. Si un campo es incompatible, el diagnóstico devuelve un error para revisarlo.

## 7. Alcance de este avance

Las propiedades adicionales que traiga la respuesta se conservan en el registro. Este contrato comprueba el subconjunto de campos requerido por el análisis del proyecto.

El diagnóstico anterior, guardado en el commit `1e39563`, confirmó acceso e identidad de las cuatro series. Las reglas ampliadas de esta etapa también se comprobaron en la ejecución reportada abajo.

La ampliación temporal agregó las comprobaciones de fechas de disponibilidad. El [diagnóstico de muestra](GUIA_MUESTRA_Y_PERFIL_ES.md) aplica un contrato de observaciones y reglas de perfil. La [cobertura histórica](GUIA_CARGA_HISTORICA_ES.md) y el [calendario hábil bancario de FIX](GUIA_CALENDARIO_Y_GOLD_ES.md) se implementaron después y forman parte de las cargas hasta Gold.

## 8. Resultado registrado

Se registró la aprobación de las veintiuna pruebas y la siguiente salida del diagnóstico real:

```text
FRED | PMAIZMTUSDM | identidad, título, unidad y frecuencia comprobados
FRED | PWHEAMTUSDM | identidad, título, unidad y frecuencia comprobados
FRED | PSOYBUSDM | identidad, título, unidad y frecuencia comprobados
Banxico | SF43718 | identidad, título, unidad y frecuencia comprobados
Comprobación finalizada: 4 series.
```

El diagnóstico aplicó también los campos de clasificación del catálogo: `NSA` para los granos y `Tipo de Cambio` para FIX. Este resultado documenta los metadatos aceptados. La comprobación real posterior de fechas y ventanas quedó en `89303ae`, la muestra de observaciones tiene su propia guía y verificación.
