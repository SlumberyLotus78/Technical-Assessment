# Guía de lectura: preparación de PostgreSQL

## 1. Propósito de este avance

El modelo y el diccionario ya describían los datos y sus relaciones. Ahora se implementó el SQL inicial y un comando que prepara una base existente, registra la versión instalada y carga las cuatro series del catálogo.

El resultado son ocho tablas del modelo y una tabla técnica de versiones. Las observaciones, resultados Gold y watermarks se pueblan mediante los comandos de carga hasta Gold. La preparación del esquema tiene su propio comando y no representa una carga histórica completada.

## 2. Organización de los archivos

| Archivo | Responsabilidad |
|---|---|
| `common/config.py` | Leer `DATABASE_URL` usando las mismas reglas privadas de las APIs. |
| `persistence/database.py` | Interpretar la conexión, exigir una base explícita y abrir la sesión. |
| `persistence/sql/001_initial.sql` | Crear esquemas, tablas, claves, restricciones e índices. |
| `persistence/schema.py` | Verificar o aplicar la versión SQL bajo un bloqueo de preparación. |
| `persistence/catalog.py` | Insertar definiciones ausentes y comprobar las existentes. |
| `persistence/initialize.py` | Coordinar el comando y confirmar o revertir la preparación. |

`persistence/__init__.py` y `persistence/sql/__init__.py` declaran paquetes regulares. El SQL se lee con `importlib.resources`, a partir del paquete. `pyproject.toml` incluye este SQL y los calendarios en el wheel, como describe la [guía de automatización](GUIA_AUTOMATIZACION_ES.md).

La función auxiliar de configuración recibe los nombres requeridos por cada componente. `load_credentials` solicita las dos claves API y `load_database_url` solicita solo la conexión. Por eso preparar PostgreSQL no exige autenticar FRED o Banxico.

## 3. Por qué usamos Psycopg

`psycopg[binary]==3.3.7` comunica Python con PostgreSQL. La variante binaria incluye las bibliotecas del cliente y simplifica la instalación en Windows. La versión quedó registrada en `requirements.txt`. [Distribución oficial](https://pypi.org/project/psycopg/3.3.7/), [instalación binaria](https://pypi.org/project/psycopg-binary/3.3.7/).

`Connection` y `Cursor` son objetos del driver. La conexión representa la sesión con la base, el cursor ejecuta consultas y obtiene resultados. El código del proyecto continúa organizado en funciones. [Uso básico de Psycopg](https://www.psycopg.org/psycopg3/docs/basic/usage.html).

Los valores se envían como segundo argumento de `execute`, usando marcadores `%s`. El driver adapta fechas, UUID y otros tipos, `Jsonb` adapta el diccionario de metadatos. Esta separación evita construir consultas concatenando valores. [Parámetros de consultas](https://www.psycopg.org/psycopg3/docs/basic/params.html).

## 4. Cómo interpretar el SQL

- `CREATE SCHEMA` organiza las tablas de `core`, `mart` y `ops`.
- `PRIMARY KEY` identifica cada fila. En observaciones combina proveedor, serie y fecha.
- `FOREIGN KEY` exige que exista la fila relacionada, como una serie o captura.
- `NOT NULL` exige un valor presente.
- `CHECK` exige una condición, como un intervalo ordenado o un valor positivo y finito.
- Los índices adicionales facilitan localizar capturas y verificaciones de una ejecución.

Una FK confirma que la captura existe, las funciones de carga comprueban además que corresponde a la misma serie y a observaciones. Un conteo FIX igual al esperado tampoco acredita por sí solo las fechas del calendario. Las reglas DQ comparan sus conjuntos de fechas antes de publicar.

PostgreSQL permite valores especiales en `NUMERIC`. Por eso el SQL excluye explícitamente `NaN`, `Infinity` y `-Infinity`, además de comprobar positividad en precios y FIX. Las variaciones porcentuales aceptan negativos, cero y `NULL`, conservando la exigencia de finitud cuando existen. [Tipos numéricos](https://www.postgresql.org/docs/18/datatype-numeric.html).

## 5. Versionado y repetición

`ops.schema_migrations` registra `version`, `checksum` y `applied_at`. El checksum identifica el SQL con saltos de línea normalizados a LF, de modo que un checkout CRLF no cambie su identidad.

En una base inicial, el comando crea las tablas y registra `001_initial`. En la segunda ejecución verifica esa misma versión y conserva las tablas. El catálogo usa `ON CONFLICT DO NOTHING` y después compara las cuatro definiciones completas: una diferencia de unidad o frecuencia produce un error en vez de sobrescribirla.

La preparación se serializa mediante un bloqueo transaccional dedicado, con un límite de espera por bloqueo de diez segundos. SQL, registro de versión y catálogo se confirman juntos. Si falla cualquier parte, se revierten los cambios del intento. [Transacciones de Psycopg](https://www.psycopg.org/psycopg3/docs/basic/transactions.html), [bloqueos transaccionales de PostgreSQL](https://www.postgresql.org/docs/18/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS).

El preparador actual corresponde a la versión inicial. Un cambio posterior requerirá un nuevo SQL y su paso de migración, el archivo aplicado se conservará. Si encuentra objetos en los esquemas del proyecto sin un registro reconocido, el comando se detiene y los preserva.

`--check-only` abre una transacción de solo lectura y comprueba versión, checksum, presencia de las nueve tablas y catálogo. Esa comprobación no sustituye una auditoría de cada alteración manual de columnas o restricciones, su alcance es el que indica el comando.

## 6. Configuración local y ejecución

Desde la raí del repositorio, con el entorno virtual activado, las dependencias se preparan con:

```powershell
python -m pip install -r requirements.txt
python -m pip check
```

El entorno utilizado para la validación de este avance ya tiene Psycopg instalado y `pip check` terminó correctamente. Estos comandos permiten reproducir la preparación en otra copia.

En el `.env` existente, completar una única variable `DATABASE_URL` con los datos de la base del proyecto. Ejemplo con contraseña de marcador:

```dotenv
DATABASE_URL=postgresql://admin:TU_CONTRASENA@localhost:5432/fred_banxico
```

Las claves API existentes se conservan. Si la contraseña tiene caracteres reservados de URL, deben codificarse en ese formato. El lector también admite la cadena de opciones PostgreSQL, por ejemplo:

```dotenv
DATABASE_URL="host=localhost port=5432 dbname=fred_banxico user=admin password='TU_CONTRASENA'"
```

Las dos líneas anteriores son alternativas, en el archivo se utiliza una sola. Las comillas o barras dentro de una contraseña deben escaparse según el formato elegido. [Formatos de conexión PostgreSQL](https://www.postgresql.org/docs/18/libpq-connect.html#LIBPQ-CONNSTRING).

La base debe existir y el rol de conexión debe tener permisos para crear sus esquemas y tablas. Si `fred_banxico` contiene otro modelo, puede prepararse una base independiente como `fred_banxico_alternativa` y utilizar ese nombre en la configuración del proyecto.

Para crear o verificar la preparación:

```powershell
python -X utf8 -m grain_pipeline.persistence.initialize --env-file .env
```

La primera ejecución debe terminar con:

```text
PostgreSQL | conexión comprobada
Esquema creado | versión: 001_initial
Tablas del modelo: 8 | tabla de versiones SQL: 1
Catálogo comprobado: 4 series.
Preparación PostgreSQL finalizada.
```

Una repetición correcta muestra `Esquema verificado`. Para comprobar sin crear objetos ni insertar catálogo:

```powershell
python -X utf8 -m grain_pipeline.persistence.initialize --env-file .env --check-only
```

El comando devuelve cero cuando completa su trabajo y uno ante un error. Los mensajes de PostgreSQL muestran el tipo de error y su SQLSTATE cuando existe, excluyen la conexión y el mensaje original del driver.

## 7. Comprobación desde pgAdmin

En el Query Tool conectado a la misma base, esta consulta muestra las tablas:

```sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema IN ('core', 'mart', 'ops')
  AND table_type = 'BASE TABLE'
ORDER BY table_schema, table_name;
```

El catálogo puede revisarse con:

```sql
SELECT provider, series_code, name, unit, frequency
FROM core.series
ORDER BY provider, series_code;
```

La preparación carga cuatro definiciones. La carga de observaciones, la certificación FIX, los resultados Gold y la inicialización del watermark corresponden al [histórico inicial](GUIA_CARGA_HISTORICA_ES.md), sus actualizaciones utilizan el [incremental](GUIA_CARGA_INCREMENTAL_ES.md) y el reproceso.

## 8. Qué se verificó realmente

La comprobación original del preparador ejecutó **83 pruebas: 72 sin servidor y 11 de integración PostgreSQL**, sin fallos ni omisiones. El entorno fue Python 3.12.4, Psycopg 3.3.7 y PostgreSQL 18.6. El [resumen de validación](evidencias/preparacion_postgres/validacion.json) conserva ese resultado y el checksum SQL comprobado. La ampliación posterior de persistencia está documentada en su [guía Silver](GUIA_PERSISTENCIA_SILVER_ES.md).

Las pruebas de integración usaron una instancia temporal local en un puerto diferente al servicio instalado. Cada caso creó y eliminó una base propia. Se verificaron repetición, modo de solo lectura, reversión, catálogo incompatible, versiones alteradas, tablas ausentes, claves, precisión, valores especiales, estados y preparación concurrente. La instancia temporal se detuvo al terminar.

La base del proyecto configurada en `.env` no se utilizó en esas pruebas. Se confirmó después su preparación y su comprobación de solo lectura, ese avance quedó en `90381bf`.

La suite puede reproducirse con:

```powershell
python -X utf8 -m unittest discover -s tests -v
```

Sin `TEST_DATABASE_URL` en el entorno, los casos que requieren servidor se omiten. La [evidencia final](evidencias/entrega_final/validacion.json) registra la suite ampliada ejecutada con PostgreSQL y cero omisiones. Una omisión en una ejecución sin conexión no equivale a una comprobación de PostgreSQL.

Para ejecutar la integración se requiere una conexión explícita a una base de prueba cuyo nombre comience por `grain_test_`, con un rol autorizado para crear bases. Cada caso crea y elimina exclusivamente una base `grain_test_<uuid>`. Los casos reciben esa conexión del entorno, el ejecutor explícito descrito a continuación puede leer `TEST_DATABASE_URL` del archivo privado antes de importar los tests.

### 8.1. Preparar la conexión de integración

Con PostgreSQL activo, abrir el Query Tool sobre `postgres` utilizando un administrador. Si el rol `admin` necesita permiso para crear las bases desechables, ejecutar:

```sql
ALTER ROLE admin CREATEDB;
```

Crear después la base de conexión, ejecutando esta sentencia por separado si aún no existe:

```sql
CREATE DATABASE grain_test_bootstrap OWNER admin;
```

El permiso `CREATEDB` permite crear bases, un superusuario ya puede hacerlo. [Requisitos de PostgreSQL](https://www.postgresql.org/docs/18/sql-createdatabase.html).

Agregar en el `.env` local la conexión de pruebas, sin reemplazar `DATABASE_URL`:

```dotenv
TEST_DATABASE_URL=postgresql://admin:TU_CONTRASENA@localhost:5432/grain_test_bootstrap
```

La contraseña se completa solo en ese archivo privado y debe codificar los caracteres reservados de una URL cuando corresponda. La base `grain_test_bootstrap` es el punto de conexión, no necesita tablas inicializadas.

Desde la raí del repositorio, ejecutar:

```powershell
python -X utf8 -m tests.run --postgres --env-file .env
```

El ejecutor lee la clave de prueba antes del descubrimiento, conserva la prioridad del entorno y no utiliza la conexión del producto como alternativa. Sin `--postgres`, `python -m tests.run` no carga el archivo privado y omite los casos SQL. El comando directo de `unittest` tampoco carga `.env` automáticamente.

Los resultados del preparador conservados arriba corresponden a su avance original. La publicación alcanzó 161 casos, la ampliación histórica [186, incluidas 53 SQL](evidencias/carga_historica/validacion.json), y el incremental [209, incluidas 68 SQL](evidencias/carga_incremental/validacion.json). La incorporación de recuperación, reprocesos y dashboard alcanzó [243 pruebas aprobadas, incluidas 87 SQL](evidencias/recuperacion_dashboard/validacion.json), sin omisiones, en una instancia temporal aislada. En ese avance, sin conexión de integración se omitían los 87 casos SQL.

El cierre de automatización amplió la comprobación a [254 casos, incluidos 91 SQL](evidencias/entrega_final/validacion.json), con cero omisiones. La suite actual omite esos 91 casos cuando no se solicita PostgreSQL, el modo `tests.run --postgres` exige que se ejecuten.

## 9. Guardar el avance

Después de preparar y comprobar la base destinada a esta rama:

```powershell
git add .env.example requirements.txt README.MD grain_pipeline tests docs
git diff --cached --stat
git commit -m "feat: prepare versioned PostgreSQL schema"
git status
```

La [guía Silver](GUIA_PERSISTENCIA_SILVER_ES.md) documenta las funciones de registro de capturas, intentos, DQ y observaciones validadas. Los coordinadores de carga, reproceso y recuperación reutilizan estas funciones y el publicador compartido hasta Gold.
