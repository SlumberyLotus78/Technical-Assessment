# Guía de lectura: fechas de disponibilidad y selección de muestra

## 1. Propósito de esta etapa

Conocer la unidad y la frecuencia de una serie permite interpretar sus datos. Su rango declarado también permite proponer qué periodo consultar. Ahora añadimos esa lectura y un plan pequeño para la primera muestra.

| Archivo | Responsabilidad |
|---|---|
| `common/dates.py` | Interpreta fechas y realiza operaciones de calendario. |
| `sources/contracts.py` | Comprueba los formatos y el orden del rango de cada proveedor. |
| `sources/sampling.py` | Decide el mes y las ventanas propuestas para el diagnóstico. |
| `sources/metadata.py` | Consulta las fuentes y presenta el plan en la terminal. |

## 2. Formatos originales y representación común

| Proveedor | Inicio | Fin | Formato esperado |
|---|---|---|---|
| FRED | `observation_start` | `observation_end` | `YYYY-MM-DD` |
| Banxico | `fechaInicio` | `fechaFin` | `DD/MM/YYYY` |

`parse_date` comprueba primero la forma del texto y después que la fecha exista en el calendario. Devuelve un objeto `date` de Python, con atributos como `year`, `month` y `day`.

`read_metadata_range` utiliza esa función y comprueba que inicio sea anterior o igual a fin. Para las series mensuales de FRED, también exige el primer día como identificador del periodo mensual. El registro de origen conserva sus textos, las fechas interpretadas se devuelven aparte.

El rango declarado es información de metadatos. La continuidad y la cobertura se comprueban después sobre los registros recibidos mediante las reglas de observaciones y publicación.

## 3. Por qué trabajamos con meses calendario

Un mes puede tener 28, 29, 30 o 31 días. Por eso `shift_month` desplaza meses mediante año y mes, y `month_end` obtiene el último día mediante `calendar.monthrange`.

Por ejemplo, retroceder un mes desde enero lleva a diciembre del año anterior. Un desplazamiento de mes devuelve su primer día, que usamos como identificador uniforme.

`parse_month` interpreta el argumento `YYYY-MM` de la terminal. El parámetro opcional `--month` permite fijar un periodo cuando queramos repetir la propuesta.

## 4. Zona horaria de operación

La fecha de referencia se obtiene una vez al iniciar el comando usando `America/Mexico_City`. Así, el cierre de mes se calcula según la zona de operación del proyecto.

`zoneinfo` pertenece a Python y utiliza datos IANA. El paquete `tzdata` proporciona esos datos cuando el sistema no los ofrece, una situación habitual en Windows. Por eso esta etapa lo incorpora a `requirements.txt`. [Documentación de zoneinfo](https://docs.python.org/3.12/library/zoneinfo.html).

## 5. Cómo se elige el mes común

El selector recibe los cuatro registros de metadatos y una fecha de referencia. Esa fecha es un argumento para que las pruebas puedan controlar el escenario sin depender del reloj del día.

1. Exige las cuatro series, sin duplicados.
2. Calcula el mes anterior a la fecha de referencia como último mes calendario cerrado.
3. Compara ese límite con el mes final declarado por cada serie.
4. Propone el más antiguo de esos límites.
5. Si se solicita un mes manualmente, comprueba que respete el límite.
6. Comprueba que cada fuente tenga un inicio declarado compatible con la ventana propuesta.

Ejemplo ficticio con fecha de referencia 2026-11-03:

| Serie | Última fecha declarada del escenario |
|---|---|
| Maíz | 2026-09-01 |
| Trigo | 2026-08-01 |
| Soya | 2026-09-01 |
| FIX | 2026-10-30 |

Octubre ya está cerrado, pero el trigo limita la propuesta común a agosto. Ese es el mes que se utilizaría en este escenario de prueba.

## 6. Tamaño de la muestra propuesta

`sample_window` propone tres meses para cada grano y un mes para FIX. Las ventanas terminan en el mismo mes.

Los tres meses mensuales permiten inspeccionar varios registros de cada grano, un mes diario aporta varias fechas para estudiar el formato del FIX. Este tamaño pertenece al diagnóstico de muestra. El [incremental](GUIA_CARGA_INCREMENTAL_ES.md) consulta las cuatro series durante toda su ventana de revisión y meses nuevos.

En el ejemplo anterior, los granos se consultarían de junio a agosto y FIX durante agosto. Una fecha mensual como 2026-08-01 identifica el periodo de agosto, la ventana de consulta termina el 31 de agosto para expresar meses completos.

El último registro FIX puede ser anterior al último día calendario del mes por su calendario de determinación. La propuesta de muestra se basa en los meses declarados. Su cobertura se evalúa después con las observaciones y el [calendario bancario aplicable](GUIA_CALENDARIO_Y_GOLD_ES.md).

## 7. Comprobaciones y comandos

En esta etapa se agregaron diecinueve casos a los veintiuno existentes. La comprobación local ejecutó los cuarenta y terminó con `OK`. Cubren formatos, calendario, límites de disponibilidad, mes abierto, cambio de año y elección manual. Ese recuento es histórico, la [validación final](VALIDACION_FINAL_ES.md) documenta la suite del cierre y la [guía PostgreSQL](GUIA_POSTGRESQL_ES.md) explica las omisiones sin conexión de prueba.

Instalar la nueva dependencia desde la raí del repositorio:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

La suite puede reproducirse como práctica con:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

Para consultar la disponibilidad real y mostrar las ventanas propuestas:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m grain_pipeline.sources.metadata --env-file .env
```

Para fijar un mes de referencia, sujeto a las mismas comprobaciones:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m grain_pipeline.sources.metadata --env-file .env --month 2026-09
```

El diagnóstico de este módulo consulta metadatos y prepara ventanas. Se confirmó su finalización correcta y se guardó el avance en `89303ae`. La descarga e inspección de observaciones se ejecuta mediante el comando separado de la [guía de muestra y perfil](GUIA_MUESTRA_Y_PERFIL_ES.md), que documenta las 63 pruebas de aquella ampliación.
