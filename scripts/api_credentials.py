"""Share API credentials using password encryption; never print secrets."""

import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import sys
import tempfile
import warnings

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from dotenv import dotenv_values


NAMES = ("FRED_API_KEY", "BANXICO_TOKEN")
FORMAT = "grain-api-credentials-v1"


def cipher(password, salt):
    kdf = Argon2id(salt=salt, length=32, iterations=3, lanes=4, memory_cost=65536)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8"))))


def validate(values):
    if not isinstance(values, dict) or set(values) != set(NAMES):
        raise ValueError("El archivo debe contener solamente las dos credenciales API.")
    if any(not isinstance(v, str) or not v.strip() or "\n" in v or "\r" in v for v in values.values()):
        raise ValueError("Las credenciales deben tener valores no vacíos de una sola línea.")
    return values


def encrypt(values, password):
    if len(password) < 16:
        raise ValueError("Usa una contraseña de al menos 16 caracteres (preferiblemente una frase larga).")
    salt = os.urandom(16)
    token = cipher(password, salt).encrypt(json.dumps(validate(values)).encode("utf-8"))
    return {"format": FORMAT, "salt": base64.b64encode(salt).decode("ascii"), "token": token.decode("ascii")}


def decrypt(document, password):
    try:
        if document["format"] != FORMAT:
            raise ValueError
        salt = base64.b64decode(document["salt"], validate=True)
        if len(salt) != 16:
            raise ValueError
        return validate(json.loads(cipher(password, salt).decrypt(document["token"].encode("ascii"))))
    except (InvalidToken, ValueError, KeyError, TypeError, AttributeError, UnicodeError) as exc:
        raise ValueError("Contraseña incorrecta o archivo cifrado inválido/alterado.") from exc


def write_env(path, values, template):
    """Replace API entries atomically, preserving other settings and comments."""
    text = (path if path.exists() else template).read_text(encoding="utf-8-sig")
    lines = []
    for line in text.splitlines():
        assignment = line.strip().removeprefix("export ").strip().split("=", 1)[0].strip()
        if assignment not in NAMES:
            lines.append(line)
    for name, value in validate(values).items():
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        lines.append(f"{name}='{escaped}'")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write("\n".join(lines) + "\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("encrypt", "decrypt"), nargs="?", default="decrypt")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--encrypted-file", type=Path, default=Path("credentials.encrypted.json"))
    parser.add_argument("--template", type=Path, default=Path(".env.example"))
    args = parser.parse_args(argv)
    try:
        # Fail closed if the terminal cannot hide input.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("Contraseña: ")
            if args.action == "encrypt":
                if args.encrypted_file.exists():
                    raise ValueError("El archivo cifrado ya existe; usa otra ruta para generar uno nuevo.")
                if password != getpass.getpass("Repite la contraseña: "):
                    raise ValueError("Las contraseñas no coinciden.")
                source = dotenv_values(args.env_file, encoding="utf-8-sig", interpolate=False)
                document = encrypt({name: source.get(name) for name in NAMES}, password)
                with args.encrypted_file.open("x", encoding="utf-8") as stream:
                    json.dump(document, stream, indent=2)
                    stream.write("\n")
                print("Archivo cifrado creado. Comparte la contraseña por separado.")
            else:
                document = json.loads(args.encrypted_file.read_text(encoding="utf-8"))
                write_env(args.env_file, decrypt(document, password), args.template)
                print("Credenciales guardadas en el archivo .env local; completa DATABASE_URL si hace falta.")
        return 0
    except (ValueError, OSError, EOFError, getpass.GetPassWarning):
        print("No se completó la operación: revisa contraseña, archivos y terminal interactiva.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
