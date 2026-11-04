"""Coordinación explícita de etapas y límites de transacción.

locking.py mantiene la exclusión del producto entre transacciones.
preparation.py reúne capturas y registra las evaluaciones previas.
publication.py confirma Silver, Gold, watermark y éxito como una unidad.
Los comandos histórico e incremental se incorporarán por separado.
"""
