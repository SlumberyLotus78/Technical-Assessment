# Recuperación de intentos y reprocesos explícitos

## 1. Operaciones distintas

El incremental actualiza el producto desde su watermark y revisa meses recientes. El reproceso consulta de nuevo un intervalo publicado que se elige explícitamente. La recuperación aprovecha originales de un intento interrumpido, si todavía es seguro reutilizarlos. Cada operación mantiene su comando y comparte las reglas y la publicación hasta Gold.

No se modifica el SQL inicial ni se agregan clases de aplicación. El reproceso conserva `load_type = historical` en el modelo existente y se distingue mediante `CTL-05` con `operation = reprocess`. La recuperación conserva la modalidad del intento de origen y registra `operation = recovery`, `source_run_id` y los identificadores de captura en el nuevo intento.

## 2. Recuperación bajo bloqueo

Una ejecución puede quedar `running` si termina su proceso o pierde la conexión. Ese estado por sí solo no prueba que siga activa. El comando obtiene primero el mismo bloqueo de sesión que utilizan las cargas, si otro proceso lo mantiene, termina sin modificar el intento.

Después consulta el estado durable y decide:

| Situación | Resultado |
|---|---|
| Intento `succeeded` o `skipped`, o recuperación directa ya aprobada | `already_completed`, sin volver a publicar. |
| Intento sin ventana planificada | `retry_required`, se necesita planificar una extracción nueva. |
| Metadatos o ventanas de observaciones incompletos | `retry_required`, no se completan las respuestas con datos inventados o antiguos de Silver. |
| Existe una publicación exitosa posterior al inicio del intento | `retry_required`, se evita restaurar valores potencialmente antiguos. |
| Conjunto registrado completo y vigente | `recovered`, si hash, contratos, cobertura y publicación vuelven a aprobarse. |

Se esperan cuatro metadatos y una respuesta por serie y ventana anual. Este control de forma no sustituye DQ: se verifican después los archivos y sus observaciones completas.

Un huérfano se cierra como `failed`, con un diagnóstico controlado de interrupción. Ese cierre se confirma antes de abrir el intento nuevo para que sobreviva a un fallo posterior. Una fila que ya estaba `failed` conserva su cierre original. No se vuelve a poner en `running` una ejecución terminada.

La nueva ejecución referencia las capturas del origen sin cambiar su propietario ni copiarlas sobre otros archivos. El manifiesto y `CTL-05` registran esa relación. Si una recuperación falla, su propio identificador permite otro intento usando los identificadores heredados, se mantienen todos los cierres anteriores.

## 3. Comando y reintentos

Desde la raí del repositorio, con el entorno virtual activo:

```powershell
python -X utf8 -m grain_pipeline.orchestration.recovery --run-id UUID_DEL_INTENTO --env-file .env
```

La recuperación no consulta APIs y no requiere sus llaves. Se debe usar el mismo `--bronze-root` de la carga original si no era `data/bronze`.

Un resultado `retry_required` utiliza código de salida `2` e imprime el comando apropiado. Hay que revisar su periodo antes de ejecutarlo. Si el intento carecía de meses y tampoco existe histórico, los marcadores `YYYY-MM` deben sustituirse por el intervalo inicial elegido. Una excepción de integridad o DQ utiliza código `1`, éxito o estado ya completado utilizan `0`.

Para localizar intentos:

```sql
SELECT run_id, load_type, status, stage, start_month, end_month, error_summary
FROM ops.runs
ORDER BY started_at DESC
LIMIT 20;

SELECT run_id, status, details
FROM ops.dq_results
WHERE rule_code = 'CTL-05'
ORDER BY checked_at DESC;
```

Si el servidor confirmó una publicación pero el cliente perdió su respuesta, el estado `succeeded` evita repetirla desde recuperación. La publicación utiliza la misma transacción para Silver, Gold, watermark y éxito, una interrupción previa al commit no deja esas escrituras parcialmente confirmadas.

## 4. Reprocesar una corrección antigua

El comando recibe ambos extremos y exige que estén dentro del intervalo publicado:

```powershell
python -X utf8 -m grain_pipeline.orchestration.reprocess --start-month 2025-01 --end-month 2025-03 --env-file .env
```

Se consultan metadatos actuales y las observaciones de esas fechas. Se preservan las respuestas, se perfilan y se invoca el publicador común. El reproceso conserva `start_month`, `published_through_month` e `initial_run_id`, después de aprobarse actualiza `last_run_id` y la fecha de confirmación. Solo cambia filas analíticas y Silver cuando cambian sus valores.

Gold se reconstruye desde el histórico Silver completo para actualizar también dependencias fuera del intervalo consultado. Por ejemplo, una revisión de julio de 2025 puede modificar su referencia, el MoM de agosto de 2025 y el YoY de julio de 2026. Una ampliación del histórico corresponde al incremental.

## 5. Módulos y artefactos

| Módulo relativo a `grain_pipeline/` | Responsabilidad |
|---|---|
| `quality/recovery.py` | Decisión pura sobre estado, ventanas y antigüedad de las capturas. |
| `quality/reprocessing.py` | Límites del intervalo que puede corregirse. |
| `persistence/recovery.py` | Lectura operativa, vínculos de capturas y cierre del huérfano. |
| `orchestration/recovery.py` | Bloqueo, intento nuevo y reutilización sin APIs. |
| `orchestration/reprocess.py` | Reconsulta del intervalo y coordinación del reproceso. |

Los originales del reproceso se guardan en `data/bronze/reprocess/<run_id>/`. Los artefactos de una recuperación aprobada se guardan en `data/bronze/recovery/<run_id>/`, mientras que sus capturas siguen en la ubicación original. Ambos conservan plan, manifiesto, perfil de entrada y `run_result.json` según la fase alcanzada.

La [evidencia conjunta](evidencias/recuperacion_dashboard/validacion.json) documenta las pruebas con PostgreSQL aislado y HTTP simulado. Se verificaron integridad, bloqueo concurrente, repetición sin duplicaciones, rechazo de capturas antiguas, correcciones con dependencias mensuales y anuales, y rollback después de modificar el watermark. Las pruebas no provocaron fallos ni modificaciones en la base del proyecto.

La recuperación es una operación explícita del operador. La [automatización](GUIA_AUTOMATIZACION_ES.md) ejecuta el incremental y registra logs, códigos de salida y timeout, no invoca automáticamente la recuperación ni el histórico. El [runbook](RUNBOOK_ES.md) indica cómo revisar el estado durable antes de recuperar. La evidencia anterior corresponde a esa etapa, la [validación final](VALIDACION_FINAL_ES.md) registra la suite del cierre.
