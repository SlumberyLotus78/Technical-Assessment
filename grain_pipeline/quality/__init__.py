"""Reglas de calidad y perfiles que pueden ejecutarse sin acceder a las APIs.

values.py interpreta valores de origen, profiling.py resume los registros.
observations.py exige su aceptación y representa los resultados por regla.
calendar.py evalúa DQ-09, gold.py comprueba el conjunto y las dependencias mensuales.
history.py exige meses cerrados, calendarios y disponibilidad de las cuatro series.
Este archivo declara quality como paquete regular de Python.
"""