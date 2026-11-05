# Configuración obligatoria de credenciales

Las claves API de FRED y Banxico se entregan cifradas en
`credentials.encrypted.json`, en la raíz del repositorio. El responsable del
proyecto proporciona la contraseña personalmente por un canal separado.

Después de instalar las dependencias principales con `requirements.txt`, ejecutar
desde la raíz del repositorio:

```powershell
.\.venv\Scripts\python.exe -m scripts.api_credentials
```

Ingresar la contraseña recibida en el indicador oculto de la terminal. Este paso
es obligatorio para configurar las credenciales API antes de ejecutar el pipeline.
No se necesita cifrar archivos ni instalar dependencias adicionales.

El script crea `.env` desde `.env.example` si no existe y guarda allí las dos
claves descifradas. Si ya existe, conserva la configuración de PostgreSQL y las
demás opciones. Completar `DATABASE_URL` con la conexión local y continuar con
el paso 4 del README.

Una contraseña incorrecta o un archivo alterado impiden modificar `.env`.
Si falta el archivo cifrado, solicitarlo al responsable del proyecto.
Las variables del proceso siguen teniendo precedencia sobre `.env`.

Las claves se protegen con Fernet y una clave derivada mediante Argon2id con sal
aleatoria. La contraseña no se almacena en el repositorio. Después de descifrar,
las claves quedan en texto claro en el `.env` privado, excluido de Git.
