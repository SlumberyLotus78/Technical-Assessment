# Resultados del análisis publicado

## 1. Datos y alcance

El análisis utiliza el Gold real de PostgreSQL, consultado mediante una instantánea de solo lectura el 4 de noviembre de 2026 UTC. La [evidencia numérica](evidencias/entrega_final/analisis_real.json) identifica la publicación `2d5eef1b-603e-4d13-97ff-360fa54e0a81`, su fecha de confirmación, el periodo y los valores utilizados. No se realizaron nuevas peticiones a FRED o Banxico para generar este informe.

El producto contiene enero de 2009 a septiembre de 2026. Se eligió enero de 2010 a septiembre de 2026 para la comparación: 201 meses comunes por grano, conservando 2009 como contexto para variaciones. El preflight instalado comprobó 5,102 observaciones Silver, 213 medias FIX y 639 referencias Gold.

Los indicadores son nominales. La referencia `precio USD/t × promedio FIX` excluye fletes, seguros, aranceles, calidad y condiciones comerciales. La atribución descompone una identidad matemática y no demuestra causalidad económica.

## 2. Cambio acumulado en pesos

| Grano | Cambio de la referencia MXN/t, enero de 2010 a septiembre de 2026 |
|---|---|
| Maíz | +90.93% |
| Trigo | +98.36% |
| Soya | +80.97% |

El trigo tiene el mayor aumento acumulado de la selección y la soya el menor. El cálculo compara la última referencia con la primera del mismo grano, manteniendo iguales los extremos temporales.

## 3. Precio internacional y referencia en pesos

En maíz, el índice del precio internacional termina **41.58%** por encima de enero de 2010, mientras que la referencia nominal en pesos aumenta **90.93%**. Los índices parten de cien para hacer comparables unidades diferentes. La diferencia entre sus recorridos refleja que el FIX también cambia durante el periodo.

La evolución no es uniforme. Los máximos intermedios del índice en pesos superan el nivel final, por lo que el cambio entre extremos no resume toda la volatilidad observada. Este informe no atribuye esas variaciones a acontecimientos económicos que no hayan sido analizados por separado.

## 4. Caídas internacionales cuyo ahorro no se reflejó en MXN

Se define un ahorro cancelado como un mes con precio internacional menor que el del mes calendario previo y referencia en pesos igual o mayor. El denominador incluye únicamente meses comparables con caída internacional.

| Grano | Meses con caída USD/t | Ahorros cancelados | Frecuencia |
|---|---|---|---|
| Maíz | 97 | 15 | 15.46% |
| Trigo | 101 | 14 | 13.86% |
| Soya | 97 | 16 | 16.49% |

En esta selección, la referencia en pesos no disminuyó en 15 de las 97 caídas mensuales internacionales de maíz. La frecuencia mayor corresponde a soya y la menor a trigo. Estas frecuencias describen los meses observados, sin constituir una probabilidad de movimientos futuros.

Los 201 meses analizados tienen comparador previo publicado. Enero de 2010 utiliza diciembre de 2009, aunque ese comparador esté fuera de la ventana visible. Si no existieran caídas elegibles, la frecuencia sería nula.

## 5. Contribución mensual de cada factor

La atribución simétrica reparte por igual la interacción entre precio y FIX. La suma de ambas contribuciones concilia con el cambio de la referencia mensual, dentro de la precisión decimal de cálculo. Las contribuciones se expresan en puntos porcentuales respecto de la referencia del mes previo. Una contribución negativa reduce el valor resultante y una positiva lo aumenta.

La [metodología del dashboard](ANALISIS_Y_DASHBOARD_ES.md) documenta las fórmulas, el tratamiento de ausencias y los límites de interpretación.

## 6. Reproducción del análisis

```powershell
python -X utf8 -m scripts.export_analysis --output-dir data/analysis_review --figures-dir data/analysis_figures
```

La exportación requiere las dependencias del dashboard, acceso de lectura a PostgreSQL y Microsoft Edge para renderizar imágenes locales en un perfil separado. Se debe elegir una carpeta nueva para conservar los informes anteriores. Los PNG son exportaciones de los mismos constructores de gráficos del dashboard, no se presentan como capturas de su ventana completa.
