# Guía de lectura: registros operativos y preparación Silver

## 1. Propósito y alcance

La base preparada permite almacenar el catálogo y las entidades del modelo. Este avance implementa funciones para registrar intentos, capturas y resultados DQ, preparar observaciones tipadas y escribir sus valores vigentes en Silver.

Las funciones de escritura se comprobaron en PostgreSQL aislado. El comando de esta guía ofrece una vista previa sobre archivos locales. Los coordinadores de carga reutilizan estas funciones y el [publicador compartido](GUIA_PUBLICACION_GOLD_ES.md), que confirma Silver, Gold, watermark y éxito como una unidad.

## 2. Separación de responsabilidades

| Archivo | Responsabilidad |
|---|---|
| `extraction/capture_reader.py` | Leer una captura dentro de Bronze, interpretar su contexto y calcular el hash. |
| `quality/observations.py` | Exigir registros aceptables y traducir el perfil a estados de reglas DQ. |
| `transformations/silver.py` | Preparar `date` y `Decimal`, ofrecer la vista previa. |
| `persistence/runs.py` | Registrar intentos, avanzar etapas y registrar fallos controlados. |
| `persistence/captures.py` | Registrar procedencia y comprobar archivos contra su registro. |
| `persistence/quality.py` | Recalcular perfiles desde capturas registradas y guardar sus evaluaciones. |
| `persistence/observations.py` | Escribir observaciones nuevas o revisadas por su clave natural. |

Las decisiones DQ permanecen en `quality/`, la preparación de datos vive en `transformations/`, las escrituras están en `persistence/`. Las funciones reciben argumentos explícitos y son compartidas por histórico, incremental, reproceso y recuperación.

## 3. Lectura e integridad de una captura

`read_capture` recibe la ruta del archivo y la raíz Bronze. Resuelve las rutas antes de leer, exige un archivo JSON dentro de esa raíz y comprueba proveedor, código, tipo, instante y ventana. Las fechas del contexto se convierten a `date` y el instante se normaliza a UTC.

El payload y el SHA-256 se obtienen de los mismos bytes. La ruta almacenada es relativa a una raíz Bronze que deberá permanecer estable para la base del proyecto. Si se reutiliza el almacenamiento desde otra ubicación, esa raíz deberá señalar los mismos archivos y estructura relativos.

`register_capture` crea el registro en `ops.raw_captures`. Si la misma ruta ya está registrada con el mismo contenido y contexto, devuelve su identificador existente. El registro conserva el intento que capturó originalmente el archivo, un reproceso puede reutilizarlo sin reasignar esa procedencia.

Si una ruta registrada cambia de hash o contexto, la operación se detiene. Una revisión de origen debe tener una captura nueva. `read_registered_capture` vuelve a comprobar la integridad al preparar o escribir los datos.

## 4. Reglas, tipos y preparación Silver

`validate_observations` aplica el perfil al conjunto de registros y exige que esté completo bajo las reglas de registros implementadas. Rechaza vacíos, duplicados, fechas fuera de ventana, fechas mensuales incompatibles y valores ausentes, inválidos o no positivos.

`prepare_observations` se ejecuta después de esa validación. Construye diccionarios con:

| Campo | Tipo Python | Significado |
|---|---|---|
| `provider` | `str` | Proveedor conocido. |
| `series_code` | `str` | Código oficial de la serie. |
| `observation_date` | `date` | Periodo mensual o día FIX. |
| `value` | `Decimal` | Número leído directamente desde texto, sin redondear. |

La salida se ordena por fecha y los registros originales se conservan. El contrato de fuente continúa comprobando la estructura nativa antes de esta preparación.

La aceptación de registros diarios no equivale a certificar su cobertura bancaria. `profile_checks` genera `DQ-09: pending` para FIX y omite las reglas exclusivamente mensuales `DQ-07` y `DQ-08`. Una respuesta diaria vacía genera además `SRC-03: failed`, aunque sus contadores de errores de fila sean cero.

## 5. Registro de intentos y evaluaciones

`begin_run` crea un intento `running` con su modalidad e intervalo. `set_run_stage` avanza sus etapas sin permitir retrocesos. `require_running_run` bloquea la fila del intento mientras se realizan sus escrituras, para que un cierre concurrente no deje operaciones posteriores sobre un intento terminado.

`fail_run` registra la etapa del fallo y un resumen de tipo de excepción o SQLSTATE. El mensaje original de una excepción externa puede incluir credenciales, por lo que se excluye del registro, las capturas y evaluaciones DQ conservan el contexto operativo.

`record_capture_profile` lee la captura registrada, verifica su integridad, comprueba el contrato de observaciones y recalcula el perfil. Guarda una evaluación por regla aplicable en `ops.dq_results`, con el ID de captura en `details`. La función genérica `record_quality_result` permite registrar también controles globales o fallos que el coordinador detecte antes de poder obtener un perfil.

Cada evaluación tiene su propio UUID: repetir una evaluación conserva un nuevo registro del intento. Una estructura de fuente incompatible debe ser tratada por el coordinador mediante su regla de contrato, una captura incompatible no se convierte en un perfil aprobado.

## 6. Escritura, repetición y revisiones

`save_capture_observations` exige un intento activo, catálogo compatible y captura íntegra de observaciones. Su ventana debe estar contenida en el intervalo planificado del intento. El conjunto completo se valida y transforma antes de comenzar las escrituras.

El SQL identifica las filas por `(provider, series_code, observation_date)`. Usa `ON CONFLICT` para insertar una fila nueva o actualizar una existente únicamente cuando cambió su valor. [Contrato de INSERT y ON CONFLICT](https://www.postgresql.org/docs/18/sql-insert.html).

Los escenarios sintéticos comprobados fueron:

| Escenario | Recibidos | Escritos | Sin cambios |
|---|---:|---:|---:|
| Primera captura mensual de tres registros | 3 | 3 | 0 |
| Repetición de esos valores | 3 | 0 | 3 |
| Nueva captura con una revisión de valor | 3 | 1 | 2 |

En una revisión se conservan la ejecución y el instante de creación. Se actualizan el valor, la captura que lo sustenta y los campos de última modificación. Las filas sin cambios conservan todos esos campos. Los archivos anteriores permanecen disponibles.

La métrica `written` reúne inserciones y actualizaciones efectivas. Psycopg acumula las filas afectadas de `executemany`, no se deduce el resultado solo del número recibido. [rowcount de Psycopg](https://www.psycopg.org/psycopg3/docs/api/cursors.html#psycopg.Cursor.rowcount).

## 7. Quién decide la transacción

Las funciones reciben la conexión y dejan la confirmación al coordinador. Exigen `autocommit=False`, de modo que este pueda revertir el conjunto. El publicador confirma el diagnóstico operativo antes de intentar publicar y agrupa las escrituras Silver, Gold, watermark y éxito en su transacción de publicación.

Se verificó con dos conexiones que los registros nuevos no eran visibles para un observador antes del commit y que un rollback los eliminaba. También se comprobaron evaluaciones DQ confirmadas que permanecían después de una escritura rechazada.

Las funciones Silver por sí solas no finalizan un histórico como satisfactorio. Esa transición pertenece al publicador, que comprueba Gold y sus dependencias. Las tablas y el SQL `001_initial` permanecen iguales, la persistencia utiliza el modelo existente.

## 8. Ejecutar la vista previa

Desde la raí del repositorio, con las capturas de muestra disponibles:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m grain_pipeline.transformations.silver
```

El comando selecciona la última carpeta de `data/bronze/samples/` cuyo perfil indique terminación y exige una captura de observaciones por serie. Puede fijarse una carpeta con `--sample-dir PATH`, `--bronze-root PATH` indica su raíz de almacenamiento.

La comprobación sobre la muestra real preparada anteriormente produjo:

```text
Banxico | SF43718 | registros preparados: 21
FRED | PMAIZMTUSDM | registros preparados: 3
FRED | PSOYBUSDM | registros preparados: 3
FRED | PWHEAMTUSDM | registros preparados: 3
Cobertura FIX para publicación: pendiente de calendario bancario.
Vista previa Silver finalizada: 30 observaciones.
```

La vista previa lee archivos, prepara tipos en memoria y muestra conteos, no escribe PostgreSQL ni inicializa el producto. Los comandos de carga invocan las funciones de persistencia mediante su coordinación hasta Gold.

## 9. Evidencia y pruebas

La [vista previa conservada](evidencias/persistencia_silver/vista_previa.json) contiene las 30 observaciones normalizadas y los hashes de las capturas reales archivadas que las sustentan. Fechas y decimales se serializan como texto para poder guardarlos en JSON, durante la preparación se comprobaron sus tipos Python.

El [resumen de validación](evidencias/persistencia_silver/validacion.json) registra **108 pruebas aprobadas: 86 sin servidor y 22 con PostgreSQL aislado**, sin fallos ni omisiones. Se utilizaron Python 3.12.4, Psycopg 3.3.7 y PostgreSQL 18.6. La instancia temporal se cerró al terminar. La comprobación de este avance no escribió en la base del proyecto.

`tests/postgres_support.py` comparte el soporte de las suites SQL, cada caso obtiene su propia base desechable. El framework llama a `setUp` antes de cada método y `addCleanup` registra el cierre y la eliminación de sus recursos. Esa clase organiza las pruebas, el código de aplicación mantiene funciones por responsabilidad.

La suite puede reproducirse con:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

En el avance documentado, sin `TEST_DATABASE_URL` se ejecutaban 86 casos sin servidor y se omitían 22 de los 108 descubiertos. Esos números se conservan como resultado histórico. El comando anterior descubre la suite disponible hoy y no carga `.env`, la [validación final](VALIDACION_FINAL_ES.md) registra su total posterior. La integración completa se solicita con `python -X utf8 -m tests.run --postgres --env-file .env`, usando la conexión de prueba dedicada descrita en la [guía PostgreSQL](GUIA_POSTGRESQL_ES.md).

## 10. Guardar el avance y continuar

Después de revisar la vista previa:

```powershell
git add README.MD grain_pipeline tests docs
git diff --cached --stat
git commit -m "feat: add validated Silver persistence and run tracking"
git status
```

La [guía de calendario y Gold](GUIA_CALENDARIO_Y_GOLD_ES.md) explica la certificación bancaria y las transformaciones mensuales incorporadas después. La [publicación Gold](GUIA_PUBLICACION_GOLD_ES.md) y el [coordinador histórico](GUIA_CARGA_HISTORICA_ES.md) completan el recorrido hasta el watermark.
