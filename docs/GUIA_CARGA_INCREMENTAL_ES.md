# Carga incremental independiente hasta Gold

## 1. Propósito y decisiones

El histórico establece el intervalo inicial del producto. El incremental utiliza ese avance para consultar meses nuevos y revisar publicaciones recientes. Tiene su propio comando y coordinador, si falta el histórico, registra el fallo y termina antes de consultar las APIs.

El watermark pertenece al producto mensual completo: tres granos, FIX certificado y referencias Gold. El último mes candidato es el menor entre el mes cerrado más reciente en `America/Mexico_City` y el último mes declarado por cada fuente. Los metadatos permiten planificar, la disponibilidad declarada no acredita por sí sola una cobertura completa.

La revisión predeterminada incluye **los últimos tres meses ya publicados**, además de todos los meses nuevos. Esta política permite detectar correcciones recientes sin consultar todo el histórico a las APIs en cada ejecución. Se eligió como parámetro operativo del proyecto, no representa una garantía sobre cuánto tiempo pueden revisar datos los proveedores. `--review-months` admite valores de cero a doce. Una corrección anterior a esa ventana utiliza el [comando de reproceso explícito](GUIA_RECUPERACION_Y_REPROCESOS_ES.md).

## 2. Cómo se selecciona la ventana

Ejemplos con watermark en septiembre de 2026 e inicio histórico en enero de 2009:

| Disponibilidad común cerrada | Revisión | Consulta de observaciones | Resultado posible |
|---|---|---|---|
| Septiembre de 2026 | 3 | Julio a septiembre de 2026. | Revisa datos, puede confirmar éxito con cero escrituras. |
| Octubre de 2026 | 3 | Julio a octubre de 2026. | Revisa tres meses y agrega octubre si aprueba sus controles. |
| Octubre de 2026 | 0 | Octubre de 2026. | Consulta únicamente el mes nuevo. |
| Diciembre de 2026 | 0 | Octubre a diciembre de 2026. | Recupera todos los meses pendientes, sin saltos. |
| Septiembre de 2026 | 0 | Ninguna. | Comprueba la publicación vigente y registra `skipped`. |

El solapamiento se limita al inicio del histórico si todavía hay menos meses publicados que los solicitados. Las consultas se dividen por año calendario cuando cruzan diciembre. Un corte opcional `--end-month YYYY-MM` debe estar entre el watermark y el último mes común cerrado, nunca reduce el avance existente.

Una fuente cuya disponibilidad declarada retroceda antes del watermark bloquea la ejecución. También se rechaza un FIX que declare un cierre diario insuficiente para el mes seleccionado. Los años sin calendario revisado, los registros ausentes o los fallos DQ impiden publicar.

Con revisión cero y un corte igual al watermark se omiten observaciones, incluso si hay meses posteriores disponibles. El plan conserva ese corte y la disponibilidad común para explicar la decisión.

## 3. Organización del código

Las rutas de esta tabla son relativas a `grain_pipeline/`.

| Módulo | Responsabilidad |
|---|---|
| `quality/incremental.py` | Precondición del histórico, meses cerrados y límites de revisión. |
| `orchestration/incremental_plan.py` | Cálculo puro de la ventana desde watermark, metadatos y parámetros. |
| `orchestration/incremental.py` | Coordinación incremental y su comando. |
| `quality/windows.py` | Contratos de disponibilidad y calendarios compartidos por ambas cargas. |
| `extraction/captures.py` | Conservación de metadatos y fragmentos de observaciones. |
| `orchestration/extraction.py` | Consultas y registro durable de cada captura antes del contrato. |
| `orchestration/artifacts.py` | Manifiesto, perfil de la ventana recibida y resumen de cierre. |
| `orchestration/failures.py` | Cierre seguro del intento fallido con diagnóstico controlado. |
| `orchestration/publication.py` | Validación global y publicación atómica compartida. |
| `persistence/runs.py` | Registro del intento y asignación de su intervalo después de planificar. |
| `persistence/watermarks.py` | Cierre publicado o cierre sin trabajo, dejando el commit al coordinador. |

Las funciones antes específicas del histórico se trasladaron a módulos comunes. El comando histórico conserva su interfaz y sus artefactos. Ambos coordinadores invocan las mismas funciones de captura, calidad, Silver y Gold, no se llaman entre sí. No se añadieron clases de aplicación, dependencias ni migraciones.

## 4. Recorrido y garantías

1. Adquiere el bloqueo del producto y comprueba esquema y catálogo.
2. Registra un intento incremental en `planning`, todavía sin intervalo de observaciones.
3. Lee el watermark y exige un histórico publicado válido.
4. Conserva los cuatro metadatos, calcula la ventana y escribe el plan.
5. Si hay trabajo, asigna el intervalo una sola vez, comprueba disponibilidad y calendarios, y conserva cada respuesta antes de validarla.
6. Genera el manifiesto y el perfil de las observaciones recibidas.
7. El publicador verifica la procedencia anterior y la nueva ventana, prepara Silver, reconstruye Gold y confirma capas, watermark y éxito juntos.

El bloqueo de sesión permanece adquirido durante el proceso. Cada petición HTTP comienza sin transacción SQL abierta. Las capturas y los diagnósticos se conservan progresivamente, las escrituras de las capas y del avance pertenecen a una sola transacción.

La extracción incremental es acotada. **El cálculo Gold utiliza el intervalo publicado completo de Silver**, incluidas las nuevas observaciones. Así conserva comparadores MoM y YoY por fecha exacta: revisar agosto puede cambiar su referencia y la variación de septiembre, revisar un FIX puede modificar las tres referencias del mes. La persistencia actualiza solo los valores analíticos que cambian y preserva la auditoría de las filas sin cambios.

Con revisión cero y sin meses seleccionados, se verifica nuevamente la procedencia Silver y la correspondencia de Gold con sus entradas. Solo entonces el intento queda `skipped` en `planning`, con fechas de intervalo nulas. No se cambia ningún campo del watermark ni de los hechos. Esta comprobación no busca revisiones nuevas en las observaciones de las APIs.

Una revisión ejecutada y aprobada queda `succeeded`, aunque no cambien valores: registra una publicación comprobada y actualiza `last_run_id`. Un fallo conserva la publicación anterior, `ops.runs` y `ops.dq_results` permiten identificar su etapa.

## 5. Artefactos

```text
data/bronze/incremental/<run_id>/
    query_plan.json
    metadata/
    observations/           # Solo cuando hay ventana seleccionada
    extraction_manifest.json
    incoming_profile.json   # Solo cuando se consultan observaciones
    run_result.json
```

El plan registra watermark anterior, fecha de operación, revisión, disponibilidad común, corte opcional, ventana y cantidad de consultas. El resumen incluye estado, avance anterior y posterior y contadores de filas recibidas, escritas y sin cambios. Un fallo temprano puede dejar solo los artefactos alcanzados, el diagnóstico SQL conserva su cierre. Si el archivo de resultado no puede escribirse después del commit, se informa esa circunstancia sin alterar el éxito ya confirmado.

Se debe conservar el mismo directorio raíz Bronze del histórico. Las observaciones persistidas mantienen referencias a sus capturas originales y se verifican antes de reutilizarlas.

## 6. Verificación realizada

La [evidencia de esta etapa incremental](evidencias/carga_incremental/validacion.json) registra **209 pruebas aprobadas: 141 sin servidor y 68 SQL**, con cero fallos, errores u omisiones. Se utilizó PostgreSQL 18.6 en un clúster temporal aislado, detenido al terminar, y HTTP simulado. En esas pruebas no se leyó el `.env` real ni se escribió en la base del proyecto. La [validación final](VALIDACION_FINAL_ES.md) documenta el total posterior de la suite y las comprobaciones reales por separado.

Los quince casos SQL nuevos comprobaron el requisito de histórico, la revisión sin cambios, correcciones de granos y FIX, ampliaciones continuas, cambio de año, omisión validada, regresión de disponibilidad, ausencia de calendario, conexión SQL inactiva durante HTTP y rollback tras modificar watermark y éxito. Ocho casos adicionales comprobaron el plan y los argumentos sin servidor.

Un caso reconstruyó el histórico ficticio 2009-01 a 2026-09 y agregó octubre con ocho consultas lógicas: cuatro de metadatos y cuatro de observaciones de julio a octubre. Terminó con 5,127 observaciones Silver, 214 medias FIX y 642 referencias Gold. Los precios y el FIX de esa prueba fueron valores ficticios de 100 y 20, estos conteos verifican el recorrido técnico y no constituyen un nuevo perfil de las APIs reales.

Se confirmó por separado que el histórico real del periodo elegido terminó con los resultados esperados. Después se registró la salida del incremental real `2d5eef1b-603e-4d13-97ff-360fa54e0a81`: revisión de julio a septiembre de 2026, 74 observaciones recibidas, cero escrituras Silver/Gold y watermark conservado en septiembre, con estado `succeeded`. Las cuatro series se consultaron durante los tres meses, por eso son 74 observaciones, frente a las 30 del diagnóstico inicial, cuyo FIX solo cubría septiembre. Esa evidencia comprueba una revisión real sin cambios, no acredita la incorporación de un mes nuevo en esa ejecución.

## 7. Ejecutar desde el repositorio

Desde la raí del repositorio, con el entorno virtual activo y la conexión de pruebas preparada:

```powershell
python -X utf8 -m tests.run --postgres --env-file .env
python -X utf8 -m grain_pipeline.orchestration.incremental --env-file .env
```

El segundo comando utiliza las APIs y la base del proyecto. No es necesario reinstalar dependencias para este avance. Si el histórico usó otro directorio Bronze, añadir el mismo `--bronze-root`.

No se supone que octubre ya esté disponible. El comando consulta los metadatos actuales. Si el último mes común sigue siendo septiembre, revisa julio–septiembre, un resultado `succeeded` con cero filas escritas es correcto cuando las fuentes no han revisado sus valores.

Después de esa ejecución, esta variante permite comprobar el cierre sin revisión cuando no hay meses nuevos seleccionados:

```powershell
python -X utf8 -m grain_pipeline.orchestration.incremental --review-months 0 --env-file .env
```

## 8. Comprobar el control y guardar el avance

En pgAdmin, revisar los intentos recientes y el watermark:

```sql
SELECT run_id, load_type, status, stage, start_month, end_month, error_summary
FROM ops.runs
ORDER BY started_at DESC
LIMIT 5;

SELECT pipeline_name, start_month, published_through_month, initial_run_id, last_run_id
FROM ops.watermarks;
```

El inicio debe seguir siendo enero de 2009. El avance solo cambia al publicar meses nuevos completos. Una revisión aprobada puede conservar el mes final y cambiar `last_run_id`, un `skipped` conserva ambos.

Guardar los archivos del avance después de verificar la ejecución:

```powershell
git status --short
git add README.MD grain_pipeline tests docs
git diff --cached --stat
git commit -m "feat: add independent incremental loading with bounded revisions"
git status
```

La [recuperación y el reproceso](GUIA_RECUPERACION_Y_REPROCESOS_ES.md) y el [dashboard](ANALISIS_Y_DASHBOARD_ES.md) amplían estos coordinadores independientes. El [wheel y la tarea programada](GUIA_AUTOMATIZACION_ES.md) ejecutan el incremental instalado. El seguimiento profesional del desarrollo permanece en [Implementación_proceso.md](Implementación_proceso.md).
