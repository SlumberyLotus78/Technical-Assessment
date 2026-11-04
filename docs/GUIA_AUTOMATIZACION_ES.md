# Wheel y automatización del incremental

## 1. Distribución

`pyproject.toml` define el paquete `grain-pipeline`, versión 1.0.0, y sus entradas de consola. Las dependencias del proceso de datos se instalan por defecto. Streamlit y Plotly pertenecen al extra opcional `dashboard`, de modo que el entorno programado no necesita esas bibliotecas.

El wheel incorpora el SQL inicial y los dieciocho calendarios anuales 2009-2026. El README forma parte de sus metadatos, se excluyen `.env`, datos generados, pruebas y la carpeta `docs/`. La estructura sigue la [guía de empaquetado de Python](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/), con backend y herramientas fijados en las dependencias de desarrollo.

| Entrada | Operación |
|---|---|
| `grain-initialize` | Preparar o comprobar el modelo. |
| `grain-historical` | Histórico inicial explícito. |
| `grain-incremental` | Meses nuevos y revisión reciente. |
| `grain-reprocess` | Reconsulta de meses publicados. |
| `grain-recover` | Recuperación explícita de un intento. |
| `grain-state` | Comprobación de solo lectura, sin APIs. |
| `grain-scheduled` | Log, código de salida y límite de tiempo del proceso instalado. |
| `grain-dashboard` | Interfaz instalada, si se agrega el extra `dashboard`. |

## 2. Construcción e instalación

Con Python 3.12.4 preparado y desde la raí del repositorio:

```powershell
python -m pip install -r requirements-dev.txt
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File scripts/build_wheel.ps1
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File scripts/install_worker.ps1
```

El constructor usa una copia nueva de los dos paquetes y los metadatos. Evita incluir módulos retirados por restos de builds anteriores. En Windows restaura en el wheel la herencia de permisos de su carpeta de salida, para que el intérprete de instalación pueda leer el archivo movido por el backend.

El artefacto se escribe en `dist/grain_pipeline-1.0.0-py3-none-any.whl`. Si ya existe, se conserva: puede elegirse otra carpeta con `-OutputDirectory`. El instalador acepta `-WheelPath` y crea `.venv-automation` si todavía no existe. Reinstala el artefacto elegido, comprueba dependencias e importa el comando incremental.

El wheel y el entorno se excluyen de Git. Las fuentes, recursos, instrucciones y evidencia de su construcción se conservan en el repositorio. Una versión nueva requiere actualizar el número de versión y verificarla antes de cambiar la instalación utilizada por la tarea.

El Control de aplicaciones de Windows bloqueó los lanzadores `.exe` generados por pip en el entorno de origen. Se utiliza el Python instalado con `-I -m`, sin modificar esa política. La verificación de las ocho entradas carga sus funciones desde los metadatos instalados y comprueba `--help`, no se presenta como ejecución de los lanzadores bloqueados. La definición de la tarea utiliza el intérprete directamente.

## 3. Comprobación previa

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File scripts/run_incremental.ps1 -CheckOnly
```

El modo de comprobación ejecuta `state` en un proceso Python aislado. Comprueba esquema, catálogo, watermark inicializado, integridad de originales, Silver y Gold en una instantánea de solo lectura. No crea intentos ni consulta APIs. La misma comprobación es obligatoria al registrar una tarea.

## 4. Programación

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File scripts/register_task.ps1 -At 20:00 -PreviewOnly
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File scripts/register_task.ps1 -At 20:00
```

La tarea `GrainPipelineLearningIncremental` requiere que Windows use la zona correspondiente a Ciudad de México. Su primer disparo se fija en una fecha futura. Ejecuta directamente el Python de `.venv-automation`, con `-I -X utf8`, el módulo `scheduled` y rutas absolutas de configuración, Bronze y logs. La acción no contiene contraseñas ni llaves de APIs.

La cuenta debe tener una sesión iniciada. Se utilizan privilegios limitados y no se guarda su contraseña en Windows Task Scheduler. El equipo y PostgreSQL deben estar disponibles, un disparo omitido puede ejecutarse cuando la sesión vuelva a estar disponible. La política `IgnoreNew` evita instancias superpuestas y el bloqueo de PostgreSQL protege también frente a ejecuciones manuales concurrentes.

El [modelo de identidades del Programador de tareas](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtaskprincipal) sustenta esta configuración. El registro rechaza una tarea ya existente, `-PreviewOnly` permite inspeccionar la definición propuesta sin reemplazarla ni registrarla.

La frecuencia diaria revisa publicaciones que llegan con retraso y correcciones recientes, aunque el producto sea mensual. Los tres meses de revisión siguen siendo configurables. El histórico y los reprocesos permanecen como operaciones explícitas.

## 5. Logs, tiempos y reintentos

Cada ejecución crea `data/logs/scheduler/<UTC_UUID>.log` y un JSON con operación, inicio, fin, estado y código de salida. El archivo de configuración no se copia al log. La salida del pipeline incluye su identificador SQL y los contadores de Silver y Gold.

El ejecutor devuelve el código del proceso hijo. Ante timeout devuelve `124`, detiene el hijo y requiere revisar el estado durable antes de recuperar. Los fallos de arranque y de validación retornan error. La tarea permite dos reintentos separados por quince minutos, con un límite de dos horas, el hijo dispone de noventa minutos. Los reintentos siguen sujetos al bloqueo, las reglas DQ y el watermark.

Una pérdida de proceso puede dejar un intento `running`, la recuperación documentada decide si pueden reutilizarse sus originales. Nunca se inicializa el histórico como respuesta automática a un fallo incremental.

## 6. Verificación realizada

Las evidencias siguientes corresponden al entorno de origen. Su inclusión en el repositorio no instala el wheel ni registra la tarea en otro equipo. La integración local y sus limitaciones se describen en la [validación final](VALIDACION_FINAL_ES.md).

La [suite final](evidencias/entrega_final/validacion.json) aprobó 254 casos: 163 sin servidor y 91 SQL, sin omisiones. La comprobación inicial del [wheel instalado](evidencias/entrega_final/wheel_installation.json) importó desde `site-packages`, sin Streamlit instalado, y recorrió histórico, incremental, reproceso, recuperación y estado con una base desechable y HTTP ficticio. La [comprobación del artefacto final](evidencias/entrega_final/wheel_final_installation.json) repite el recorrido y comprueba `--help` de las funciones registradas de las ocho entradas mediante Python, sin ejecutar los lanzadores `.exe` bloqueados.

La [evidencia de registro](evidencias/entrega_final/automation.json) conserva el horario y la próxima ejecución que indicaba el programador al registrar la tarea, sin identidad de Windows ni rutas privadas. El [smoke del scheduler](evidencias/entrega_final/scheduler_smoke.json) ejecutó una tarea temporal real con `--check-only`, terminó con código cero y retiró esa tarea. No modificó las tablas del producto ni consultó APIs. Esta comprobación se distingue del primer disparo futuro de carga incremental.

Para reproducir el smoke de solo lectura puede ejecutarse `scripts/test_scheduler.ps1` con otra ruta de informe, no sustituye la tarea diaria.
