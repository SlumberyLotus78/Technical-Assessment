"""Construye desde una copia nueva y mínima para excluir secretos y restos de otros builds."""

import argparse
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile


def build_wheel(project_root: Path, output_directory: Path) -> dict:
    """Usa el backend estándar en un directorio temporal distinto en cada invocación."""
    project_root, output_directory = project_root.resolve(), output_directory.resolve()
    metadata = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    version = metadata["project"]["version"]
    target = output_directory / f"grain_pipeline-{version}-py3-none-any.whl"
    if target.exists():
        raise ValueError("El wheel ya existe; elige un directorio de salida nuevo para conservarlo.")
    output_directory.mkdir(parents=True, exist_ok=True)
    scratch = project_root / "data" / "builds"
    if not scratch.resolve().is_relative_to(project_root):
        raise ValueError("El directorio temporal debe permanecer dentro del proyecto.")
    scratch.mkdir(parents=True, exist_ok=True)
    # TemporaryDirectory solo retira la copia UUID que creó dentro de scratch.
    # Nunca se elimina un directorio build calculado a partir de texto externo.
    with tempfile.TemporaryDirectory(prefix="wheel_", dir=scratch) as temporary:
        source = Path(temporary)
        for name in ("pyproject.toml", "README.MD"):
            shutil.copy2(project_root / name, source / name)
        for package in ("grain_pipeline", "app"):
            shutil.copytree(project_root / package, source / package,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        completed = subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(output_directory)],
                                   cwd=source, check=False)
        if completed.returncode != 0:
            raise RuntimeError("Falló la construcción del wheel.")
    if sys.platform == "win32":
        # El backend mueve el archivo desde su temporal. Se hereda la ACL de
        # dist para que otro interprete del mismo usuario pueda instalarlo.
        subprocess.run(["icacls.exe", str(target), "/reset"], stdout=subprocess.DEVNULL, check=True)
    with zipfile.ZipFile(target) as archive:
        names = set(archive.namelist())
        required = {"grain_pipeline/persistence/sql/001_initial.sql", "app/streamlit_app.py",
                    *(f"grain_pipeline/sources/calendars/{year}.json" for year in range(2009, 2027))}
        if not required <= names or any(any(part.startswith(".env") for part in name.split("/"))
                                       or name.startswith(("tests/", "docs/", "data/")) for name in names):
            raise RuntimeError("El contenido del wheel no corresponde a la entrega esperada.")
    return {"filename": target.name, "version": version, "sha256": sha256(target.read_bytes()).hexdigest(),
            "bytes": target.stat().st_size, "calendar_resources": 18, "sql_resources": 1,
            "private_configuration_included": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Construye el wheel desde una copia limpia del código.")
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        result = build_wheel(root, args.output_dir)
    except (ValueError, RuntimeError, OSError) as error:
        print(str(error) if isinstance(error, (ValueError, RuntimeError)) else "No se pudo preparar el artefacto.", file=sys.stderr)
        return 1
    print(f"Wheel: {args.output_dir / result['filename']}")
    print(f"SHA-256: {result['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
