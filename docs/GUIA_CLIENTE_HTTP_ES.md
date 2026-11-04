# Guía de lectura: cliente HTTP y primera consulta de metadatos

## 1. Qué incorpora esta etapa

La configuración prepara las claves. El cliente HTTP utiliza esas claves para enviar una petición. El módulo de metadatos decide qué serie consultar e interpreta la ubicación de su identificador en la respuesta.

| Componente | Responsabilidad |
|---|---|
| `sources/catalog.py` | Define las series y sus identificadores esperados. |
| `common/config.py` | Lee la configuración privada indicada. |
| `clients/http.py` | Envía GET, aplica autenticación y comprueba la respuesta HTTP y JSON. |
| `clients/retry.py` | Define los fallos transitorios reintentables y las esperas acotadas. |
| `sources/metadata.py` | Selecciona los endpoints y coordina la comprobación de cada serie. |
| `sources/contracts.py` | Aplica las reglas de entrada de los metadatos. |

## 2. Vocabulario del cliente

- **GET:** solicitud para consultar información.
- **Endpoint:** dirección de una operación de la API.
- **Parámetros:** valores de consulta, como el identificador de serie.
- **Encabezados:** información adicional de la petición, como el formato aceptado.
- **Respuesta:** resultado devuelto por el servidor, que incluye estado, encabezados y cuerpo.
- **JSON:** formato estructurado que `response.json()` convierte en objetos Python.

FRED recibe `series_id`, `file_type=json` y su `api_key` como parámetros. Banxico utiliza la ruta `series/{codigo}` y recibe su token mediante `Bmx-Token`. Los contratos están documentados por [FRED](https://fred.stlouisfed.org/docs/api/fred/series.html) y [Banxico](https://www.banxico.org.mx/SieAPIRest/service/v1/doc/consultaSeries), el [token de Banxico](https://www.banxico.org.mx/SieAPIRest/service/v1/token) tiene su propia documentación.

## 3. Cómo recorrer request_json

1. Comprueba el proveedor, la ruta relativa y la separación de credenciales.
2. Construye la URL y copia los parámetros del llamador.
3. Añade la autenticación correspondiente al proveedor.
4. Usa `session.get(...)` para enviar la solicitud.
5. Comprueba HTTP 200, tipo de contenido JSON y un objeto JSON como raíz.
6. Devuelve el diccionario recibido.
7. Cierra la respuesta mediante `finally`, incluso si ocurre un error.

`TIMEOUT = (10, 30)` configura la espera para conectar y la espera de lectura. No representa un límite total de duración. `requests.Session()` permite reutilizar conexiones y ofrece un administrador de contexto que cierra la sesión al terminar. Véanse las [esperas](https://requests.readthedocs.io/en/latest/user/quickstart/#timeouts) y las [sesiones de Requests](https://requests.readthedocs.io/en/latest/user/advanced/#session-objects).

El cliente permite hasta tres intentos por llamada, incluido el inicial, ante los fallos transitorios descritos en la sección 8. Esta política se incorporó con la carga histórica y también se utiliza en los diagnósticos. `max_attempts=1` limita una prueba específica a un solo intento.

## 4. Por qué controlamos los mensajes de error

La URL de FRED incorpora su clave por contrato. Algunas excepciones de la librería podrían incluir esa URL. Por ello construimos mensajes con el proveedor, el estado HTTP o el tipo de excepción, y usamos `raise ... from None` para suprimir la presentación de la excepción original.

Las redirecciones quedan desactivadas. Una respuesta distinta de HTTP 200 solo puede reintentarse si su estado pertenece a la política transitoria, en los demás casos, o al agotar los intentos, produce un error controlado. Los mensajes del diagnóstico se construyen con información pública del catálogo.

## 5. Las nuevas pruebas simuladas

La primera versión reunió seis casos HTTP, tres de metadatos y cuatro de configuración: trece en total. Contratos, fechas y selección de muestra ampliaron la suite a cuarenta, la [muestra de observaciones](GUIA_MUESTRA_Y_PERFIL_ES.md) la llevó a 63. Son recuentos de esas etapas, no el total actual de los archivos de pruebas. La [validación final](VALIDACION_FINAL_ES.md) documenta la suite completa.

`Mock` representa una sesión o una respuesta cuyo resultado controlamos. `return_value` define lo que devuelve una llamada, `side_effect` puede hacer que lance una excepción. Los métodos `assert_called_once_with` y `assert_not_called` comprueban cómo se utilizó el objeto simulado. [Documentación de Mock](https://docs.python.org/3.12/library/unittest.mock.html).

En las pruebas HTTP se ejecuta el cliente real del proyecto con una sesión simulada. En las pruebas de metadatos se ejecuta `fetch_metadata` y se sustituye el transporte por una respuesta preparada. Así se puede comprobar cada responsabilidad por separado.

Al leer estos archivos aparecen algunas formas de Python adicionales:

- `session, response = make_session(...)` reparte los dos objetos devueltos entre dos nombres.
- `session, _ = ...` indica por convención que el segundo objeto no se utilizará en ese caso.
- `{**params, "api_key": valor}` construye un diccionario copiando las entradas de `params` y agregando otra entrada.
- `self.subTest(...)` distingue las variantes de un mismo caso, esas variantes no aumentan el número de métodos de prueba.
- `patch("grain_pipeline.sources.metadata.request_json", ...)` sustituye temporalmente la referencia que utiliza el módulo de metadatos.

```powershell
python -X utf8 -m unittest discover -s tests -v
```

Las peticiones HTTP de estas pruebas utilizan comunicación simulada. El comando no carga `.env`, los casos SQL solo se ejecutan si `TEST_DATABASE_URL` ya está definida en el entorno. La [guía PostgreSQL](GUIA_POSTGRESQL_ES.md) explica cómo solicitar expresamente esa integración.

## 6. La comprobación con credenciales reales

Completar los valores de `FRED_API_KEY` y `BANXICO_TOKEN` únicamente en el archivo privado `.env` del proyecto. La función de configuración mantiene la prioridad de las variables del entorno del proceso sobre el archivo.

Las claves se gestionan mediante [FRED](https://fred.stlouisfed.org/docs/api/api_key.html) y [Banxico](https://www.banxico.org.mx/SieAPIRest/service/v1/token).

Después, desde la raí del repositorio:

```powershell
python -X utf8 -m grain_pipeline.sources.metadata --env-file .env
```

Este comando sí lee la configuración real e intenta cuatro solicitudes de metadatos: tres a FRED y una a Banxico. Cada línea satisfactoria identifica el proveedor y el código esperado. Si falla un paso, el proceso informa el error y devuelve código 1, si completa todos, devuelve 0.

El diagnóstico inicial confirmó recepción de JSON e identidad. La versión actual también aplica los contratos de título, unidad, frecuencia, clasificación y fechas. La muestra, el [histórico](GUIA_CARGA_HISTORICA_ES.md), el [incremental](GUIA_CARGA_INCREMENTAL_ES.md) y el reproceso utilizan el mismo cliente, las cargas invocan el publicador compartido hasta Gold.

### Resultado inicial registrado

El diagnóstico real finalizó con esta salida pública:

```text
FRED | PMAIZMTUSDM | metadatos recibidos e identificador comprobado
FRED | PWHEAMTUSDM | metadatos recibidos e identificador comprobado
FRED | PSOYBUSDM | metadatos recibidos e identificador comprobado
Banxico | SF43718 | metadatos recibidos e identificador comprobado
Comprobación finalizada: 4 series.
```

Este resultado, correspondiente al avance `1e39563`, acredita las consultas autenticadas y la identidad, mientras las pruebas de `unittest` utilizan escenarios simulados. La comprobación real posterior de los contratos ampliados está registrada en la [guía de contratos](GUIA_CONTRATOS_METADATA_ES.md). Ambos tipos de evidencia se documentan por separado.

## 7. Cómo funciona el comando Python

`main()` interpreta `--env-file`, lee las credenciales y recorre `SERIES`. `argparse` construye la interfaz de argumentos. El bloque `if __name__ == "__main__"` invoca `main()` al ejecutar el módulo como programa, al importarlo quedan disponibles sus funciones.

`sys.exit(main())` entrega al sistema operativo el código devuelto. La [automatización](GUIA_AUTOMATIZACION_ES.md) utiliza los códigos de salida para registrar el resultado del proceso incremental.

## 8. Reintentos incorporados con la carga histórica

El cliente utiliza ahora hasta tres intentos GET para fallos transitorios de conexión y los estados 429, 500, 502, 503 y 504. La política está separada en `clients/retry.py`, la autenticación y el contrato JSON permanecen en `http.py`.

Las respuestas se cierran antes de la espera. `Retry-After` se respeta en segundos o como fecha HTTP, una espera mayor a 30 segundos detiene la petición sin reintentar antes de lo indicado. Los errores permanentes y los contratos incompatibles siguen siendo bloqueantes. `max_attempts=1` permite comprobar un único intento en pruebas específicas.

La [guía de carga histórica](GUIA_CARGA_HISTORICA_ES.md) describe la política y sus pruebas. Los resultados iniciales anteriores conservan el contexto del avance en que se obtuvieron.
