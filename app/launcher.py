"""Entrada de consola del dashboard opcional incluido en el wheel."""

import argparse
from importlib.resources import files
from importlib.util import find_spec
import os
from pathlib import Path
import subprocess
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Abre el dashboard instalado contra PostgreSQL.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        print("El puerto debe estar entre 1 y 65535.", file=sys.stderr)
        return 1
    if find_spec("streamlit") is None:
        print("Instala el extra del dashboard: pip install 'grain-pipeline[dashboard]'.", file=sys.stderr)
        return 1
    script = files("app").joinpath("streamlit_app.py")
    command = [sys.executable, "-I", "-m", "streamlit", "run", str(script), "--server.address", "127.0.0.1",
               "--server.port", str(args.port), "--browser.gatherUsageStats", "false"]
    if args.headless:
        command.extend(["--server.headless", "true"])
    environment = dict(os.environ, GRAIN_ENV_FILE=str(args.env_file.resolve()))
    try:
        return subprocess.call(command, env=environment)
    except OSError:
        print("No se pudo iniciar el dashboard instalado.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
