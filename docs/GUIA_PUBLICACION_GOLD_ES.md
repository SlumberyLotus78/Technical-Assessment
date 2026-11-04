# Persistencia Gold y publicación transaccional

## 1. Qué se incorpora

Las transformaciones anteriores preparan Silver, certifican FIX y calculan Gold. Este paso incorpora la escritura Gold y la coordinación que confirma Silver, Gold, watermark y éxito como una unidad.

La implementación recibe un intento y sus capturas ya registrados y confirmados. Se comprobó con capturas ficticias y PostgreSQL real en bases desechables. Los coordinadores histórico, incremental, de reproceso y de recuperación invocan estas mismas funciones.

## 2. Organización por responsabilidad

| Módulo | Responsabilidad |
|---|---|
| `sources/contracts.py` | Revalidar también el registro de metadatos conservado en Bronze. |
| `quality/publication.py` | Continuidad del intervalo, conjunto de capturas, duplicados globales, meses faltantes, procedencia y comparación Gold. |
| `persistence/gold.py` | Leer Silver comprobando sus originales y guardar Gold por sus claves naturales. |
| `persistence/watermarks.py` | Comprobar el origen del avance y cerrar watermark y estado exitoso. |
| `persistence/locking.py` | Consultas SQL para adquirir y liberar el bloqueo del producto. |
| `persistence/quality.py` | Registro de perfiles y resultados, permite evaluar DQ-09 mensual sin insertar un pendiente de diagnóstico por captura. |
| `orchestration/locking.py` | Mantener el bloqueo mientras se confirman varias transacciones. |
| `orchestration/preparation.py` | Reunir las capturas y registrar sus validaciones antes de escribir las capas. |
| `orchestration/publication.py` | Coordinar preparación, publicación atómica y registro de fallos. |
| `tests/run.py` | Ejecutar la suite con integración PostgreSQL explícita y exportar un resumen opcional. |

No se agregaron clases de aplicación ni dependencias. Las clases nuevas corresponden a `unittest.TestCase`. El archivo `001_initial.sql` conserva su contenido y checksum: las tablas y campos necesarios ya estaban definidos.

## 3. Contrato del publicador

`publish_registered_captures` recibe:

| Parámetro | Significado |
|---|---|
| `connection` | Conexión dedicada, transaccional y sin trabajo pendiente. |
| `run_id` | Intento durable en estado `running`, con meses explícitos y etapa previa a Silver. |
| `capture_ids` | Identificadores únicos de capturas registradas. |
| `bronze_root` | Raíz estable desde la que se resuelven las rutas Bronze. |
| `as_of` | Fecha de operación usada para exigir meses cerrados. |

Las entradas requieren un registro de metadatos por cada serie y capturas de observaciones de las cuatro series. Se admiten varios fragmentos de observaciones, pero sus ventanas deben estar contenidas en el intervalo del intento y el conjunto debe estar completo y sin duplicados.

Las respuestas nuevas deben certificar por sí mismas el intervalo solicitado. Una fila antigua de Silver no puede completar silenciosamente una fecha omitida por la nueva respuesta. Después se combinan los valores nuevos con el histórico vigente para reconstruir los comparadores y resultados dependientes.

Los metadatos se revalidan desde su registro archivado mediante `validate_metadata_record`. Es la misma lógica de identidad, unidad, frecuencia, título y disponibilidad utilizada tras una consulta API. No se construye una respuesta API artificial alrededor del registro archivado.

## 4. Transacciones y fallos

```mermaid
flowchart TD
    A[Intento y capturas confirmados] --> B[Bloqueo de sesión del producto]
    B --> C[Validar fuentes, procedencia y cobertura]
    C --> D[Confirmar resultados DQ]
    D --> E[Escribir Silver]
    E --> F[Recalcular y guardar Gold]
    F --> G[Verificar valores y completar watermark y éxito]
    G --> H[Commit de publicación]
    E -. fallo .-> R[Rollback de publicación]
    F -. fallo .-> R
    G -. fallo .-> R
    R --> L[Registrar fallo en otra transacción]
    H --> U[Liberar bloqueo]
    L --> U
```

Existen dos límites principales dentro del publicador:

1. La preparación registra calidad y confirma sus resultados antes de modificar las capas.
2. La publicación escribe Silver, Gold, watermark y estado `succeeded`, y confirma todo junto.

Si una regla Python falla durante la preparación, se conservan las evaluaciones realizadas, incluidas las fallidas o pendientes. Si una operación SQL invalida esa transacción, se revierte antes de registrar el diagnóstico general. Un fallo durante la escritura revierte todas las modificaciones de las capas y registra después el intento como `failed`, con su etapa y un resumen controlado.

El tipo de error y, cuando corresponde, SQLSTATE explican el fallo sin guardar el texto original de excepciones externas. Las métricas DQ conservan los faltantes y demás detalles públicos. El comportamiento de commit y rollback sigue el [contrato de transacciones de Psycopg](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).

El finalizador también comprueba Silver y Gold antes de cerrar el watermark. Cambiar manualmente la etapa a `publication` no permite declarar éxito con tablas vacías.

## 5. Bloqueo entre ejecuciones

Un bloqueo de sesión PostgreSQL permanece adquirido aunque se confirme la fase DQ o se revierta una transacción. Esa duración permite serializar todo el trabajo del publicador. El bloqueo tiene identificador distinto del utilizado al instalar el esquema. [Bloqueos consultivos de PostgreSQL](https://www.postgresql.org/docs/18/explicit-locking.html#ADVISORY-LOCKS).

`product_publication_lock` es una función con `@contextmanager`. El código anterior a `yield` adquiere el recurso, el bloque `finally` revierte trabajo pendiente y libera el bloqueo al salir del `with`, incluso ante una excepción. La función exige una conexión sin transacción pendiente para no confirmar trabajo de otro proceso.

Si otra sesión tiene el bloqueo, la función falla sin esperar indefinidamente y sin modificar el intento recibido. Los coordinadores adquieren este mismo ámbito desde la planificación y mantienen confirmados sus registros antes de invocar la publicación.

## 6. Procedencia, repetición y revisiones

La lectura Silver verifica el hash y contexto de cada captura referenciada y comprueba que su serie, fecha y valor correspondan al registro almacenado. Un valor modificado manualmente en SQL o un archivo Bronze alterado bloquean su reutilización.

Gold se reconstruye para el intervalo publicado completo. Así conserva el contexto anterior a un mes revisado y los comparadores necesarios para MoM y YoY. La escritura usa `ON CONFLICT` y modifica solo las filas cuyos campos analíticos cambiaron. Se comparan los valores completos, tener el mismo número de filas no basta. [Actualización por conflicto en PostgreSQL](https://www.postgresql.org/docs/18/sql-insert.html#SQL-ON-CONFLICT).

| Escenario ficticio verificado | Comportamiento |
|---|---|
| Histórico inicial de septiembre | 24 observaciones Silver, una media FIX, tres referencias y watermark inicial. |
| Nueva ejecución con los mismos valores | Cero escrituras de hechos, conserva los instantes e identificadores de auditoría de Silver y Gold. |
| Revisión del precio de maíz de agosto dentro de julio-septiembre | Una observación Silver modificada, cambian la referencia de agosto y la variación de septiembre. |
| Incremental de octubre tras septiembre | Amplía el extremo final y conserva el inicio y la ejecución histórica inicial. |
| Incremental sin histórico o con un salto de meses | Rechaza la publicación y conserva el avance previo. |
| Fallo después de escribir Gold o de actualizar el watermark | Revierte las capas y el cierre de éxito, conserva capturas y diagnóstico. |

El watermark registra la última publicación confirmada aunque una repetición no cambie valores. Los campos de auditoría de los hechos identifican la ejecución que realmente cambió sus datos.

## 7. Verificación realizada

La [evidencia de esta etapa](evidencias/publicacion_gold/validacion.json) registra **161 pruebas aprobadas, con cero fallos, errores u omisiones**: 118 sin servidor y 43 de PostgreSQL. Incluye 21 pruebas nuevas de publicación SQL, siete de reglas puras y tres de configuración del ejecutor. Es un resultado histórico, la [validación final](VALIDACION_FINAL_ES.md) documenta la suite ampliada del cierre.

Se utilizó Python 3.12.4 y PostgreSQL 18.6. La instancia temporal local escuchó en un puerto separado del servicio del proyecto. Cada caso SQL creó y eliminó su base `grain_test_<uuid>` y usó capturas ficticias. La instancia temporal se detuvo al terminar. No se leyó el `.env` privado del proyecto ni se escribieron datos en su base.

Una prueba abrió otra conexión después de actualizar las capas y el watermark, pero antes del commit. Esa conexión siguió viendo la publicación anterior. Después del commit se comprobó el nuevo avance. Otras pruebas inyectaron fallos después de las escrituras para verificar la reversión.

La evidencia se generó invocando `tests.run` con `--postgres --report` desde un script auxiliar en línea que inició y detuvo la instancia temporal. El ejecutor del repositorio produjo los contadores y la lista de casos SQL ejecutados, el script añadió el contexto del clúster y su cierre. La preparación local del clúster continúa siendo independiente del ejecutor de pruebas.

## 8. Cómo comprobar este paso

Con PostgreSQL activo y la conexión de prueba configurada en el `.env` local:

```dotenv
TEST_DATABASE_URL=postgresql://admin:TU_CONTRASENA@localhost:5432/grain_test_bootstrap
```

La base debe existir y el rol de conexión necesita permiso para crear bases. La [guía PostgreSQL](GUIA_POSTGRESQL_ES.md) incluye su preparación. La variable `DATABASE_URL` del producto permanece independiente.

Desde la raí del repositorio, con `.venv` activado:

```powershell
python -X utf8 -m tests.run --postgres --env-file .env
```

Este comando reemplaza el bloque de Python en línea que cargaba la conexión manualmente. Lee `TEST_DATABASE_URL` antes de importar las pruebas SQL, una variable de entorno explícita tiene prioridad sobre el archivo. No utiliza `DATABASE_URL` como alternativa y exige cero omisiones para devolver éxito con `--postgres`.

Para ejecutar solo los casos sin servidor:

```powershell
python -X utf8 -m tests.run
```

En ese modo no carga `.env` y desactiva la conexión de prueba del proceso. En el avance original ejecutaba 118 casos y omitía 43 de PostgreSQL, en el cierre documentado ejecuta 163 y omite 91. El comando habitual `python -m unittest discover -s tests -v` utiliza `TEST_DATABASE_URL` si ya está configurada en el entorno, pero no carga el archivo automáticamente.

Se puede conservar otro resumen con `--report`, la carpeta debe existir y el archivo debe ser nuevo:

```powershell
New-Item -ItemType Directory -Path data -Force | Out-Null
python -X utf8 -m tests.run --postgres --env-file .env --report data/validacion_publicacion.json
```

No se requiere reinstalar dependencias ni ejecutar una migración SQL. Después de revisar las pruebas:

```powershell
git status --short
git add .env.example README.MD grain_pipeline tests docs
git diff --cached --stat
git commit -m "feat: publish Silver Gold and watermark atomically"
git status
```

## 9. Alcance de la evidencia y componentes relacionados

Estas pruebas acreditan el publicador y la persistencia con datos ficticios. La muestra archivada y sus vistas previas conservan su evidencia real inicial. Posteriormente, se confirmó la carga histórica real de 2009-01 a 2026-09 y su revisión incremental sin cambios, el preflight instalado verificó mediante lecturas las capas y sus originales. La [validación final](VALIDACION_FINAL_ES.md) distingue esas comprobaciones de las pruebas simuladas.

La [recuperación explícita](GUIA_RECUPERACION_Y_REPROCESOS_ES.md) comprueba el estado durable bajo el bloqueo del producto antes de reintentar, el cliente puede no haber recibido la respuesta del servidor. Reutiliza capturas completas y rechaza reproducirlas después de otra publicación. Un estado previo inconsistente con Bronze o Gold sigue siendo bloqueante. La [automatización](GUIA_AUTOMATIZACION_ES.md) programa el incremental y registra sus resultados, la recuperación permanece como una operación explícita del operador.

La [guía histórica](GUIA_CARGA_HISTORICA_ES.md) conecta la extracción inicial con estas funciones. El [incremental](GUIA_CARGA_INCREMENTAL_ES.md) mantiene su propio comando y planificación sobre el watermark. La evidencia original del publicador se conserva, la [verificación conjunta posterior](evidencias/recuperacion_dashboard/validacion.json) amplía los casos de recuperación y lectura analítica.
