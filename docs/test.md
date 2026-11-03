# Guía de pruebas



| Nombre | Situación preparada | Comportamiento esperado |
|---|---|---|
| `test_file_values_remain_literal_and_accept_utf8_bom` | Archivo con BOM y una clave que contiene `${SUFFIX}` | Leer las claves y conservar esa expresión sin sustituirla. |
| `test_environment_value_overrides_file_value` | Clave FRED diferente en archivo y entorno | Elegir FRED del entorno y Banxico del archivo. |
| `test_empty_environment_value_requires_correction` | Clave FRED vacía en el entorno y con contenido en archivo | Lanzar `ValueError`, señalando que FRED necesita corregirse. |
| `test_missing_credential_message_excludes_available_value` | Archivo con FRED, sin Banxico | Identificar la variable ausente y preservar el valor privado disponible. |

Estas comprobaciones verifican reglas de configuración. La autenticación y la disponibilidad de las APIs tendrán sus propias comprobaciones.


## 2. Salidas

- `ok`: el caso satisfizo las condiciones que comprobamos.
- `FAIL`: una comprobación no obtuvo lo esperado.
- `ERROR`: ocurrió una excepción inesperada durante la preparación o ejecución.
- `Ran 4 tests`: se ejecutaron cuatro casos.
- `OK`: el conjunto terminó satisfactoriamente.