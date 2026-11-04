"""Conexión, preparación y comprobación del modelo PostgreSQL.

database.py abre conexiones, schema.py aplica y verifica el SQL versionado.
catalog.py prepara el catálogo, initialize.py coordina el comando de terminal.
runs.py, captures.py y quality.py registran los intentos y su evidencia.
observations.py escribe observaciones validadas por su clave natural.
gold.py comprueba Silver y escribe agregados y referencias, watermarks.py
verifica el avance y cierra el éxito, locking.py reserva el bloqueo del producto.
"""
