"""Verifica el wheel fuera del checkout usando una base UUID y HTTP ficticio."""

import argparse
from datetime import date
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from grain_pipeline.extraction.raw import write_json
from grain_pipeline.sources.catalog import SERIES
from tests.historical_fixtures import historical_session
from tests.run import read_test_database_url


# Este programa de prueba se ejecuta con el Python instalado y -I. Importa
# codigo productivo exclusivamente de site-packages y recibe respuestas JSON
# ficticias por archivo, sin agregar el checkout a sys.path.
INSTALLED_PROBE = r'''
from copy import deepcopy
from datetime import datetime
from importlib.metadata import distribution, version
from importlib.util import find_spec
import json
from pathlib import Path
import sys
from unittest.mock import MagicMock, Mock, patch

import grain_pipeline
import requests
from grain_pipeline.orchestration import historical, incremental, recovery, reprocess, state
from grain_pipeline.persistence.initialize import main as initialize
from grain_pipeline.persistence.schema import schema_resource
from grain_pipeline.sources.banking_calendar import banking_calendar_for_month
from datetime import date

root = Path(sys.argv[1])
fixture = json.loads((root / 'responses.json').read_text(encoding='utf-8'))
assert Path(grain_pipeline.__file__).resolve().is_relative_to(Path(sys.prefix).resolve() / 'Lib/site-packages')
assert find_spec('streamlit') is None
for year in range(2009, 2027):
    assert banking_calendar_for_month(date(year, 1, 1)) is not None
session = MagicMock(spec=requests.Session)
session.__enter__.return_value = session
session.__exit__.return_value = False
def get(url, *, params, headers, timeout, allow_redirects):
    if 'api.stlouisfed.org' in url:
        code = params['series_id']
        observations = url.endswith('series/observations')
        payload = deepcopy(fixture[code]['observations' if observations else 'metadata'])
        if observations:
            payload['observations'] = [row for row in payload['observations'] if params['observation_start'] <= row['date'] <= params['observation_end']]
            payload['count'] = len(payload['observations'])
    else:
        parts = url.split('/')
        observations = 'datos' in parts
        payload = deepcopy(fixture['SF43718']['observations' if observations else 'metadata'])
        if observations:
            payload['bmx']['series'][0]['datos'] = [row for row in payload['bmx']['series'][0]['datos']
                if parts[-2] <= datetime.strptime(row['fecha'], '%d/%m/%Y').date().isoformat() <= parts[-1]]
    response = Mock(status_code=200, headers={'Content-Type': 'application/json'})
    response.json.return_value = payload
    return response
session.get.side_effect = get
arguments = ['--env-file', str(root / 'fixture.env'), '--bronze-root', str(root / 'bronze')]
assert initialize(['--env-file', str(root / 'fixture.env')]) == 0
with patch('requests.Session', return_value=session), \
     patch.object(historical, 'datetime') as history_time, patch.object(incremental, 'datetime') as incremental_time, \
     patch.object(reprocess, 'datetime') as reprocess_time:
    for clock in (history_time, incremental_time, reprocess_time):
        clock.now.return_value = datetime(2026, 11, 3)
    assert historical.main(['--start-month', '2026-07', '--end-month', '2026-09', *arguments]) == 0
    assert incremental.main(arguments) == 0
    fixture['PMAIZMTUSDM']['observations']['observations'][1]['value'] = '125'
    assert reprocess.main(['--start-month', '2026-08', '--end-month', '2026-08', *arguments]) == 0
with patch.object(state, 'datetime') as state_time:
    state_time.now.return_value = datetime(2026, 11, 3)
    assert state.main([*arguments, '--report', str(root / 'state.json')]) == 0
result = json.loads((root / 'state.json').read_text(encoding='utf-8'))
assert (result['silver_rows'], result['fx_months'], result['grain_references']) == (74, 3, 9)
assert recovery.main(['--run-id', result['initial_run_id'], *arguments]) == 0
receipt = {'successful': True, 'version': version('grain-pipeline'), 'imported_from_installed_environment': True,
    'dashboard_dependency_installed': find_spec('streamlit') is not None, 'calendar_years_checked': 18,
    'sql_checksum_lf': schema_resource()[1], 'fixture_api_calls': session.get.call_count,
    'silver_rows': result['silver_rows'], 'fx_months': result['fx_months'], 'grain_references': result['grain_references'],
    'console_entry_points': sorted(entry.name for entry in distribution('grain-pipeline').entry_points),
    'project_database_written': False, 'real_api_requests_made': False}
for entry in distribution('grain-pipeline').entry_points:
    try:
        entry.load()(['--help'])
    except SystemExit as result:
        assert result.code == 0
    else:
        raise AssertionError('The help parser did not finish normally.')
receipt['console_entry_points_tested'] = len(receipt['console_entry_points'])
receipt['entry_point_verification_method'] = 'installed main(argv) functions with --help via trusted Python'
receipt['native_console_launchers_executed'] = False
receipt['supported_execution_method'] = 'python -I -m'
(root / 'installed_receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
'''


def fixture_responses() -> dict:
    """Prepara las cuatro respuestas nativas con la misma fixture de integracion existente."""
    session, responses = historical_session(), {}
    for series in SERIES:
        if series["provider"] == "FRED":
            url = "https://api.stlouisfed.org/fred/series"
            params = {"series_id": series["code"]}
            observations_url = url + "/observations"
            observation_params = {**params, "observation_start": "2026-07-01", "observation_end": "2026-09-30"}
        else:
            url = "https://www.banxico.org.mx/SieAPIRest/service/v1/series/SF43718"
            params = {}
            observations_url = url + "/datos/2026-07-01/2026-09-30"
            observation_params = {}
        options = {"headers": {}, "timeout": (10, 30), "allow_redirects": False}
        responses[series["code"]] = {"metadata": session.get(url, params=params, **options).json(),
                                     "observations": session.get(observations_url, params=observation_params, **options).json()}
    return responses


def verify_installed(worker_python: Path, test_database_url: str, scratch: Path) -> dict:
    """Crea y retira exclusivamente la base grain_test_release_UUID de esta comprobacion."""
    name = "grain_test_release_" + uuid4().hex
    if re.fullmatch(r"grain_test_release_[0-9a-f]{32}", name) is None:
        raise ValueError("Nombre de prueba incompatible.")
    scratch.mkdir(parents=True)
    environment = dict(os.environ)
    for key in ("DATABASE_URL", "FRED_API_KEY", "BANXICO_TOKEN", "PYTHONPATH", "PYTHONHOME"):
        environment.pop(key, None)
    with psycopg.connect(test_database_url, autocommit=True, connect_timeout=10) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
        try:
            fixture_url = make_conninfo(test_database_url, dbname=name)
            (scratch / "fixture.env").write_text("DATABASE_URL=" + fixture_url + "\nFRED_API_KEY=fixture-key\nBANXICO_TOKEN=fixture-token\n", encoding="utf-8")
            write_json(scratch / "responses.json", fixture_responses())
            probe = scratch / "probe.py"
            probe.write_text(INSTALLED_PROBE, encoding="utf-8")
            with (scratch / "verification.log").open("w", encoding="utf-8") as output:
                result = subprocess.run([str(worker_python), "-I", "-X", "utf8", str(probe), str(scratch)],
                                        cwd=scratch, env=environment, stdout=output, stderr=subprocess.STDOUT, timeout=120)
            if result.returncode != 0:
                raise RuntimeError("Fallo la comprobacion instalada; revisar verification.log en la carpeta de prueba.")
            receipt = json.loads((scratch / "installed_receipt.json").read_text(encoding="utf-8"))
            result = subprocess.run([str(worker_python), "-I", "-X", "utf8", "-m", "grain_pipeline.orchestration.scheduled",
                                     "--env-file", str(scratch / "fixture.env"), "--bronze-root", str(scratch / "bronze"),
                                     "--log-root", str(scratch / "scheduler_logs"), "--check-only"],
                                    cwd=scratch, env=environment, capture_output=True, timeout=60)
            if result.returncode != 0:
                raise RuntimeError("Fallo el preflight programado del wheel instalado.")
            receipt["scheduled_readiness_exit_code"] = result.returncode
            return receipt
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Comprueba el wheel en un interprete separado y PostgreSQL de prueba.")
    parser.add_argument("--worker-python", type=Path, default=Path(".venv-automation/Scripts/python.exe"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        root = Path(__file__).resolve().parents[1]
        scratch = root / "data" / "verification" / ("installed_" + uuid4().hex)
        receipt = verify_installed(args.worker_python.resolve(), read_test_database_url(args.env_file), scratch)
        receipt["test_database_removed"] = True
        write_json(args.report, receipt)
    except (ValueError, RuntimeError, OSError, psycopg.Error):
        print("No se pudo completar la prueba del wheel; revisar la configuracion de prueba y su log local.", file=sys.stderr)
        return 1
    print("Wheel instalado comprobado: historico, incremental, reproceso, recuperacion, estado y preflight programado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
