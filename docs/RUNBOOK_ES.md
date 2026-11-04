# Operación del producto de granos y FIX

## 1. Requisitos operativos

Mantener PostgreSQL disponible, la configuración privada local y los archivos Bronze originales. El entorno `.venv-automation` debe contener el wheel instalado. El programador utiliza la sesión iniciada de la cuenta de ejecución y la hora de Ciudad de México.

Los calendarios revisados cubren 2009-2026. Antes de publicar datos de un nuevo año debe incorporarse y revisarse su recurso bancario con procedencia y hash. El proceso bloquea los años sin referencia, en lugar de inferir un calendario certificado.

## 2. Comprobar y ejecutar

Desde la raí del repositorio:

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File scripts/run_incremental.ps1 -CheckOnly
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File scripts/run_incremental.ps1
```

El primer comando solo consulta el producto. El segundo consulta fuentes y puede publicar una revisión o meses nuevos. Un `succeeded` con cero escrituras de hechos es correcto cuando la revisión no encuentra cambios. Con revisión cero y sin meses seleccionados puede cerrar `skipped`.

En el entorno de origen, el Control de aplicaciones bloqueó los lanzadores `.exe` de pip. Los scripts anteriores utilizan el Python permitido con `-I -X utf8 -m`. Para otros comandos instalados se utiliza el mismo patrón, por ejemplo `.\.venv-automation\Scripts\python.exe -I -X utf8 -m grain_pipeline.orchestration.recovery --run-id UUID --env-file .env`. No es necesario modificar la política de seguridad.

## 3. Revisar la tarea y los logs

```powershell
Get-ScheduledTask -TaskName GrainPipelineLearningIncremental
Get-ScheduledTaskInfo -TaskName GrainPipelineLearningIncremental
Get-ChildItem data/logs/scheduler | Sort-Object LastWriteTime -Descending | Select-Object -First 10
```

El último resultado del programador debe interpretarse con su hora de ejecución. Una tarea registrada que todavía no se ha disparado no acredita una carga programada completada. La evidencia de instalación y del smoke de solo lectura se conserva por separado.

En PostgreSQL:

```sql
SELECT run_id, load_type, status, stage, start_month, end_month, started_at, finished_at, error_summary
FROM ops.runs ORDER BY started_at DESC LIMIT 20;

SELECT pipeline_name, start_month, published_through_month, initial_run_id, last_run_id, updated_at
FROM ops.watermarks;

SELECT run_id, rule_code, status, period_start, period_end, details
FROM ops.dq_results WHERE status IN ('failed', 'pending')
ORDER BY checked_at DESC LIMIT 30;
```

## 4. Resolver un fallo

| Condición | Acción |
|---|---|
| Conexión o credenciales | Corregir la configuración local y repetir el preflight. |
| Fuente incompleta o contrato cambiado | Revisar las capturas y DQ, repetir la extracción cuando la fuente sea compatible. |
| Otra carga mantiene el bloqueo | Esperar su cierre y revisar su estado, no forzar una segunda publicación. |
| Timeout o proceso interrumpido | Consultar `ops.runs`, recuperar el identificador correspondiente después de comprobar su estado durable. |
| Corrección fuera del solapamiento | Ejecutar el reproceso explícito del intervalo publicado. |
| Captura ausente o hash distinto | Restaurar el original verificado desde su respaldo, no editar el registro para ocultar la diferencia. |
| Año bancario sin referencia | Revisar e incorporar el recurso anual antes de volver a publicar ese año. |

La [guía de recuperación](GUIA_RECUPERACION_Y_REPROCESOS_ES.md) define los comandos y el tratamiento de capturas completas, incompletas y anteriores a otra publicación. Un resultado `retry_required` requiere la extracción indicada, no se eliminan logs ni watermarks para reiniciar. Los reintentos del programador ejecutan el incremental de nuevo, la recuperación de un intento concreto requiere una decisión explícita del operador.

## 5. Actualizar una versión

Deshabilitar primero la tarea durante una ventana de mantenimiento, construir y verificar el nuevo wheel, instalarlo en un entorno preparado y comprobar su estado contra las mismas rutas Bronze. Conservar el artefacto anterior para poder reinstalarlo si la comprobación falla. Una actualización del paquete no reemplaza los originales ni modifica el esquema implícitamente. Deshabilitar la tarea impide nuevos disparos, pero no detiene una ejecución ya activa: comprobar su cierre antes de cambiar el entorno instalado.

```powershell
Disable-ScheduledTask -TaskName GrainPipelineLearningIncremental
# Instalar y verificar la versión elegida conforme a la guía de automatización.
Enable-ScheduledTask -TaskName GrainPipelineLearningIncremental
```

Los scripts de registro no sobrescriben tareas existentes. Si cambian las rutas de despliegue, se debe revisar y actualizar la definición concreta durante esa ventana.

## 6. Respaldos y conservación

Respaldar conjuntamente PostgreSQL, Bronze y la configuración privada mediante el mecanismo local elegido por el operador. Las filas Silver dependen de sus capturas, un respaldo exclusivo de las tablas no permite completar la verificación de procedencia.

Los logs del scheduler y las capturas son acumulativos. Su archivado debe preservar los originales referenciados por `ops.raw_captures` y las filas vigentes. Esta entrega no instala una política automática de borrado.

## 7. Consulta visual y entrega

El dashboard usa consultas de solo lectura y muestra exclusivamente el intervalo confirmado. Desde el checkout se abre con el comando Streamlit del [README](../README.MD). En el entorno del wheel requiere el extra `dashboard`, en este equipo se usa `.\.venv-automation\Scripts\python.exe -I -X utf8 -m app.launcher --env-file .env` por el bloqueo de los lanzadores `.exe`. Los resultados exportados y su interpretación están en [RESULTADOS_ANALISIS_ES.md](RESULTADOS_ANALISIS_ES.md).
