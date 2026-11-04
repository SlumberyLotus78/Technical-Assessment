"""Ejecución programada del paquete instalado, con log exclusivo y límite de duración."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from grain_pipeline.extraction.raw import write_json
from grain_pipeline.quality.incremental import DEFAULT_REVIEW_MONTHS, validate_review_months


def execute_scheduled(env_file: Path, bronze_root: Path, log_root: Path, *, review_months: int,
                      timeout_seconds: int, check_only: bool = False) -> dict:
    """El hijo importa el wheel en modo aislado; se conserva el código de salida real."""
    validate_review_months(review_months)
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 7200:
        raise ValueError("El límite programado debe estar entre uno y 7200 segundos.")
    env_file, bronze_root, log_root = env_file.resolve(), bronze_root.resolve(), log_root.resolve()
    if not env_file.is_file():
        raise ValueError("No existe el archivo privado de configuración de la tarea.")
    log_root.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    identifier = started.strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid4().hex
    log_file = log_root / f"{identifier}.log"
    # -I ignora PYTHONPATH y el directorio de trabajo para evitar ejecutar por
    # accidente el checkout en lugar del paquete instalado en este intérprete.
    module = "state" if check_only else "incremental"
    command = [sys.executable, "-I", "-X", "utf8", "-m", f"grain_pipeline.orchestration.{module}",
               "--env-file", str(env_file), "--bronze-root", str(bronze_root)]
    if not check_only:
        command.extend(["--review-months", str(review_months)])
    with log_file.open("x", encoding="utf-8", newline="\n") as output:
        try:
            completed = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT,
                                       timeout=timeout_seconds, check=False,
                                       **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}))
            exit_code, status = completed.returncode, "succeeded" if completed.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            output.write("La ejecución excedió su límite. Consultar el estado durable antes de recuperar el intento.\n")
            exit_code, status = 124, "timeout"
        except OSError:
            output.write("No se pudo iniciar el intérprete del paquete instalado.\n")
            exit_code, status = 1, "launch_failed"
    result = {"execution_id": identifier, "started_at_utc": started.isoformat(),
              "finished_at_utc": datetime.now(timezone.utc).isoformat(), "operation": module,
              "status": status, "exit_code": exit_code, "log_file": log_file.name,
              "review_months": None if check_only else review_months}
    try:
        write_json(log_root / f"{identifier}.json", result)
    except OSError:
        print("El proceso terminó; no se pudo exportar el resumen del scheduler.", file=sys.stderr)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ejecuta el incremental instalado y conserva log y código de salida.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--bronze-root", type=Path, default=Path("data/bronze"))
    parser.add_argument("--log-root", type=Path, default=Path("data/logs/scheduler"))
    parser.add_argument("--review-months", type=int, default=DEFAULT_REVIEW_MONTHS)
    parser.add_argument("--timeout-seconds", type=int, default=5400)
    parser.add_argument("--check-only", action="store_true", help="Comprueba la publicación sin consultar APIs ni cargar datos.")
    args = parser.parse_args(argv)
    try:
        result = execute_scheduled(args.env_file, args.bronze_root, args.log_root,
                                   review_months=args.review_months, timeout_seconds=args.timeout_seconds, check_only=args.check_only)
    except (ValueError, OSError) as error:
        print(str(error) if isinstance(error, ValueError) else "No se pudo conservar el log programado.", file=sys.stderr)
        return 1
    print(f"Scheduler | {result['status']} | código: {result['exit_code']} | log: {args.log_root / result['log_file']}")
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
