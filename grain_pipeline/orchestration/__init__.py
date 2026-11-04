"""Coordinación explícita de etapas y límites de transacción.

locking.py mantiene la exclusión del producto entre transacciones.
preparation.py reúne capturas y registra las evaluaciones previas.
publication.py confirma Silver, Gold, watermark y éxito como una unidad.
historical.py coordina la carga inicial explícita, profiling.py consolida su perfil.
El comando incremental se incorporará por separado sobre el avance publicado.
"""
