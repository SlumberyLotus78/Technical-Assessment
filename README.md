# Technical-Assessment

This repository contains a technical assessment for a Data Engineer position.

The project is designed as an end-to-end data engineering pipeline, covering data extraction, transformation, analysis, and visualization. It combines international corn, wheat, and soybean prices from FRED with the Banco de México FIX exchange rate to analyze monthly grain price references in Mexican pesos.

## Work Plan

The project scope, proposed structure, and implementation phases are described in the [implementation plan](PLAN_IMPLEMENTACION_ES.md).

## Development Environment

- Python 3.12.4, specified in `.python-version`.
- Local virtual environment in `.venv`.
- Python and pip commands run through the virtual environment.
- PostgreSQL server with an administrator account configured.
- Private configuration and generated files excluded through `.gitignore`.

The commands below use Windows PowerShell. Run them from the directory containing this README and `requirements.txt`.

## Data Sources

| Provider | Series | Identifier | Unit | Frequency |
|---|---|---|---|---|
| FRED | Corn | [PMAIZMTUSDM](https://fred.stlouisfed.org/series/PMAIZMTUSDM) | USD per metric ton | Monthly |
| FRED | Wheat | [PWHEAMTUSDM](https://fred.stlouisfed.org/series/PWHEAMTUSDM) | USD per metric ton | Monthly |
| FRED | Soybeans | [PSOYBUSDM](https://fred.stlouisfed.org/series/PSOYBUSDM) | USD per metric ton | Monthly |
| Banco de México | FIX exchange rate | SF43718 | MXN per USD | Daily |

FRED and Banco de México API credentials are supplied in `credentials.encrypted.json`. Request the decryption password directly from the project owner before setup.

## Setup

### 1. Prepare the Python Environment

Use Python 3.12.4 to create the virtual environment:

```powershell
if (-not (Test-Path -LiteralPath .venv)) {
    python -m venv .venv
}
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Direct dependencies and their versions are defined in `requirements.txt`.

### 2. Prepare the PostgreSQL Database

Before running the database initializer, have the following configured:

- A running PostgreSQL server and an administrator account authorized to create the project database.
- An existing login role with a password. The examples use `admin` as the project role and database owner.
- A dedicated database named `fred_banxico`, or another name matching the connection configuration.

In pgAdmin, connect with the administrator account and open the Query Tool on a maintenance database such as `postgres`. If the project database does not exist, run this statement separately:

```sql
CREATE DATABASE fred_banxico OWNER admin;
```

Replace `admin` with the configured project login role. Database creation requires an administrator with the appropriate privileges, as described in [CREATE DATABASE](https://www.postgresql.org/docs/18/sql-createdatabase.html).

The project account must be able to connect to the database, create the `core`, `mart`, and `ops` schemas, and own the objects it creates. Using the project database owner provides these permissions in the standard setup. See [PostgreSQL privileges](https://www.postgresql.org/docs/18/ddl-priv.html).

If you choose another database name, use that same name in `DATABASE_URL`.

### 3. Configure Private Credentials

Decrypt the supplied API credentials. This is a required setup step, the project owner sends you the password separately:

```powershell
.\.venv\Scripts\python.exe -m scripts.api_credentials
```

Enter the password at the hidden terminal prompt. The script creates `.env` from
`.env.example` if needed and writes the decrypted FRED and Banxico credentials.
It preserves other existing settings. Then edit the PostgreSQL connection
in your local `.env`:

```dotenv
DATABASE_URL=postgresql://admin:YOUR_PASSWORD@localhost:5432/fred_banxico
```

Use your actual host, port, login role, password, and database name. Reserved characters in a URL password must be percent-encoded. Process environment variables take precedence over values in `.env`.

The configuration template is tracked in Git. The private `.env` file is excluded through `.gitignore`.

See the [credential setup guide](docs/CREDENCIALES_CIFRADAS_ES.md) for details.

### 4. Initialize and Verify the Database

Prepare the database schemas, tables, SQL version record, and source catalog:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m grain_pipeline.persistence.initialize --env-file .env
```

The initializer creates eight model tables and the technical `ops.schema_migrations` table, then inserts the four source definitions. Repeating the command verifies a compatible installation and preserves existing catalog definitions.

Check the installed SQL version, tables, and catalog in read-only mode:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m grain_pipeline.persistence.initialize --env-file .env --check-only
```

## Source Validation and Sample Extraction

### Validate Source Metadata

```powershell
.\.venv\Scripts\python.exe -X utf8 -m grain_pipeline.sources.metadata --env-file .env
```

This command validates series identities, titles, units, frequencies, classifications, and declared date ranges. It proposes a common closed month and sample query windows using the `America/Mexico_City` operating timezone.

### Download and Profile a Sample

```powershell
.\.venv\Scripts\python.exe -X utf8 -m grain_pipeline.extraction.sample --env-file .env
```

The sample contains three months for each monthly grain series and one month for daily FIX observations, ending in the same month. To select the final month explicitly, use `--month YYYY-MM`, and the command checks its availability before querying observations.

Each execution saves its captures and `profile.json` under:

```text
data/bronze/samples/<execution>/
```

The profile reports missing values, invalid formats, non-positive values, dates outside the requested window, duplicate dates, and monthly coverage. The [quality rules](docs/REGLAS_CALIDAD_ES.md) define the validation and publication requirements, including banking-calendar checks for FIX.

Use `--output-dir PATH` to choose another sample root directory. The default `data/` directory is excluded from Git. A nonzero exit code indicates an error or a data quality finding that requires review.

## Preview Silver Records

```powershell
.\.venv\Scripts\python.exe -X utf8 -m grain_pipeline.transformations.silver
```

This command reads the latest complete sample under `data/bronze/samples/`, validates its observations, prepares dates and decimal values in memory, and displays the row counts. Use `--sample-dir PATH` to select a sample and `--bronze-root PATH` to specify its storage root.

## Preview Monthly Gold References

Choose the closed month covered by the FIX sample. For a September 2026 sample:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m grain_pipeline.transformations.gold_preview --month 2026-09
```

The command validates all four observation captures, compares FIX dates with the reviewed banking calendar, calculates the monthly mean FIX, and produces three grain references in MXN per metric ton. It runs locally from the sample files.

Use `--sample-dir PATH` and `--bronze-root PATH` to select an explicit sample. Add `--output PATH` to create a JSON report with source hashes, calendar evidence, and calculated values. The destination directory must exist, and existing files are rejected.

Each requested year requires a reviewed calendar resource under `grain_pipeline/sources/calendars/`. Missing calendar evidence or incomplete monthly inputs block the calculation.

## Run the Initial Historical Load

The historical command requires the prepared PostgreSQL schema, API credentials, and a product with no published watermark. Run it with an explicit interval of closed months:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m grain_pipeline.orchestration.historical --start-month 2009-01 --end-month 2026-09 --env-file .env
```

The command validates metadata availability and reviewed banking calendars, downloads observations in calendar-year windows, saves and registers each capture, and generates a consolidated profile. It then publishes Silver, Gold, the watermark, and the successful run status in one transaction.

Historical files are stored under `data/bronze/historical/<run_id>/`. They include the query plan, original captures, extraction manifest, historical profile, and publication result. Use `--bronze-root PATH` to choose another storage root.

Banking-calendar resources cover 2009–2026. Other years require reviewed references. A source contract, coverage, or publication failure preserves its available captures and diagnostic records.

## Run the Incremental Load

Run this independent command after a historical load has published successfully:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m grain_pipeline.orchestration.incremental --env-file .env
```

The command reads the product watermark and current source metadata. It requests new closed months available to all four series, together with the last three published months to check for revisions. Availability, reviewed calendars, and complete observations are required before publication. It never starts the historical command automatically.

Use `--review-months N` to select zero to twelve published months for review. With `--review-months 0`, only new months are requested, and an empty selected range triggers validation of the existing publication followed by a `skipped` run without changing the watermark. With review enabled, an unchanged window can finish successfully with zero fact rows written.

Use `--end-month YYYY-MM` to cap the update between the current watermark and the latest common closed month. Incremental API requests cover the selected window. Gold is rebuilt from the complete validated Silver history to retain exact monthly and annual comparators, with writes limited to changed rows. Silver, Gold, the watermark, and successful run status are committed together.

Incremental artifacts are stored under `data/bronze/incremental/<run_id>/`, including `query_plan.json`, original captures, `extraction_manifest.json`, `incoming_profile.json` when observations are requested, and `run_result.json`. Keep the same `--bronze-root PATH` used for the historical load: existing Silver provenance requires those original files.

## Reprocess Published Months

Use an explicit reprocessing window to check source revisions outside the regular incremental review:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m grain_pipeline.orchestration.reprocess --start-month 2025-01 --end-month 2025-03 --env-file .env
```

Both endpoints must be inside the published historical interval. The command fetches fresh metadata and observations, applies the shared quality rules, and republishes through Gold. It retains the product's initial and final months and recalculates affected monthly and annual comparators. Artifacts are stored in `data/bronze/reprocess/<run_id>/`.

## Recover an Interrupted Run

Use the run identifier from the console or `ops.runs`:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m grain_pipeline.orchestration.recovery --run-id RUN_UUID --env-file .env
```

Recovery acquires the product lock before deciding whether an unfinished attempt is abandoned. Complete registered captures can be verified and published under a new run, preserving their original ownership. Recovery makes no API requests and requires only the database configuration. An already successful run or recovery is reported without another publication.

Missing capture windows or a later successful publication require fresh extraction, and the command prints the appropriate historical, incremental, or reprocessing instruction and exits with code `2`. Failed hash, data-quality, or publication checks block recovery. Keep the original Bronze root available.

## Open the Dashboard

Install the dependencies and start the local app from the repository directory:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py --server.address 127.0.0.1
```

Open `http://localhost:8501`. The app reads the published PostgreSQL product and provides monthly range and grain filters, indexed USD/MXN evolution, monthly price/FX contributions, and cumulative comparisons across all three grains. It displays source units, certified FIX coverage, and the scope of the reference calculation.

The dashboard uses `READONLY_DATABASE_URL` when that key is present in the process environment or configuration file. It falls back to `DATABASE_URL` only when the key is absent, and an explicitly empty value must be corrected. It forces a read-only, repeatable-read transaction with bounded waits in either case. A dedicated read-only login is recommended, with minimal grants listed in the [dashboard guide](docs/ANALISIS_Y_DASHBOARD_ES.md). The app does not require API credentials. Use the `GRAIN_ENV_FILE` environment variable to select a private configuration file other than `.env`.

## Build and Install the Wheel

Install the development tools, build the package, and prepare a separate environment for automation:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File scripts/build_wheel.ps1
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File scripts/install_worker.ps1
```

The builder copies only the application packages and package metadata to a new temporary build directory. The wheel includes the SQL resource and all reviewed banking calendars, with this README embedded in its package metadata. Private configuration, local captures, tests, and the `docs/` directory are excluded. The output is `dist/grain_pipeline-1.0.0-py3-none-any.whl`, and existing artifacts are preserved. Use `-OutputDirectory PATH` for another build directory and `-WheelPath PATH` when installing that artifact.

The automation environment in `.venv-automation` installs only the data pipeline dependencies. Its console commands are `grain-historical`, `grain-incremental`, `grain-reprocess`, `grain-recover`, `grain-initialize`, `grain-state`, and `grain-scheduled`. `grain-dashboard` requires the optional dashboard extra:

```powershell
.\.venv-automation\Scripts\python.exe -m pip install ".\dist\grain_pipeline-1.0.0-py3-none-any.whl[dashboard]"
```

Console commands accept `--help`. The installed pipeline can run outside the repository, provided that configuration and Bronze paths are absolute. The scheduler uses Python's isolated mode to import the installed wheel.

Windows Application Control may block the executable launchers generated by pip. Use the installed Python directly, as configured by the scheduler scripts:

```powershell
.\.venv-automation\Scripts\python.exe -I -X utf8 -m grain_pipeline.orchestration.incremental --env-file .env --bronze-root data/bronze
.\.venv-automation\Scripts\python.exe -I -X utf8 -m grain_pipeline.orchestration.state --env-file .env --bronze-root data/bronze
```

With the dashboard extra installed, use `python -I -m app.launcher --env-file PATH` from that environment. These module commands use the same entry functions as the console launchers.

## Schedule the Incremental on Windows

Verify the published product and register the daily task:

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File scripts/run_incremental.ps1 -CheckOnly
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File scripts/register_task.ps1 -At 20:00
```

The preflight checks the schema, catalog, historical watermark, original captures, Silver, and Gold using read-only queries. Registration requires Windows to use the Mexico City timezone and refuses to replace an existing task. Add `-PreviewOnly` to inspect its XML without registering it.

The task `GrainPipelineIncremental` runs daily at 20:00 under the current logged-in Windows account, with limited privileges and no password stored in the task. PostgreSQL and the original Bronze files must remain accessible. Missed runs can start when the session becomes available. Overlapping task instances are ignored, and the product lock also prevents concurrent publication.

Each run writes a unique UTF-8 log and JSON result under `data/logs/scheduler/`. The executor preserves the pipeline exit code and enforces a 90-minute timeout. The historical command is never scheduled. To run the installed incremental manually, call `scripts/run_incremental.ps1` without `-CheckOnly`.

The [operations runbook](docs/RUNBOOK_ES.md) covers logs, retries, recovery, and updating a release.

## Tests

All **259 delivery tests passed: 168 offline and 91 PostgreSQL integration cases**, with zero failures, errors or skipped cases. The [test catalog](docs/CATALOGO_PRUEBAS_ES.md) describes all 32 modules and lists every case. The [test results summary](docs/evidencias/entrega_final/resumen_pruebas.json) records the result, Python and PostgreSQL versions, and the executed SQL cases.

Run the test suite:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

Tests use fixtures, archived captures, and simulated API responses. PostgreSQL integration tests require `TEST_DATABASE_URL` pointing to a dedicated database whose name begins with `grain_test_`, using an account with permission to create databases and roles (`CREATEDB` and `CREATEROLE`). Each integration case creates and removes its own `grain_test_<uuid>` database.

The direct `unittest` command does not load `.env`. Integration tests are skipped when `TEST_DATABASE_URL` is not set in the process environment. Their connection is independent of the project database.

To load the test connection explicitly from the private `.env` file, add:

```dotenv
TEST_DATABASE_URL=postgresql://admin:YOUR_PASSWORD@localhost:5432/grain_test_bootstrap
```

Use an existing test database and a login role authorized to create databases and roles. Run the complete suite with PostgreSQL required:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m tests.run --postgres --env-file .env
```

The runner reads only the test connection key, validates the database prefix, and requires zero skipped cases in this mode. It never uses `DATABASE_URL` as a fallback. To run without PostgreSQL or private configuration, use `python -m tests.run`.

Add `--report PATH` to create a JSON summary. The destination directory must exist and the file must be new.

To verify a wheel installation against disposable PostgreSQL and simulated HTTP:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.verify_installed_wheel --report data/wheel_verification.json --env-file .env
```

This verification reads only `TEST_DATABASE_URL`, creates and removes its own `grain_test_release_<uuid>` database, and imports the application from the separate installed environment. It never uses the project database connection as a fallback.

## Architecture and Analysis

The [analysis report](docs/RESULTADOS_ANALISIS_ES.md) explains the published reference changes and calculation scope. The [data model](docs/MODELO_DATOS_ES.md) documents the architecture and operating controls.

## Project Structure

```text
grain_pipeline/
    clients/          Authenticated HTTP communication
    common/           Configuration, dates, and decimal calculation policy
    extraction/       Source captures and sample extraction
    orchestration/    Separate load commands, shared capture steps, locking, and publication
    persistence/      PostgreSQL setup, run records, provenance, and data writes
        sql/          Versioned SQL resources
    quality/          Record, coverage, and monthly dependency rules
    sources/          Series catalog, contracts, source queries, and banking calendars
    transformations/  Typed Silver records, monthly FIX, and Gold references
tests/                Unit and PostgreSQL integration tests
app/                  Read-only dashboard queries, analytical metrics, and interactive charts
.streamlit/           Dashboard theme and telemetry configuration
scripts/              Wheel construction, installation, scheduler setup, and delivery exports
docs/                 Technical documentation and evidence
data/                 Local generated captures and reports
dist/                 Generated wheel artifacts, excluded from Git
```

## Documentation

- [Design justification and dashboard screenshots](Entregables/Justificacion_dise%C3%B1o.md)
- [Data model](docs/MODELO_DATOS_ES.md)
- [Data dictionary](docs/DICCIONARIO_DATOS_ES.md)
- [Data-quality rules](docs/REGLAS_CALIDAD_ES.md)
- [Test catalog and current results](docs/CATALOGO_PRUEBAS_ES.md)
- [Dashboard and analytical methodology](docs/ANALISIS_Y_DASHBOARD_ES.md)
- [Operations runbook](docs/RUNBOOK_ES.md)
- [Published analytical results](docs/RESULTADOS_ANALISIS_ES.md)
- [Initial data profiling](docs/Perfilamiento_inicial.md)
- [Implementation process](docs/Implementación_proceso.md)

Supporting technical documents are written in Spanish.

## Acknowledgments

Source data is provided by FRED and Banco de México. AI assistance was used for coding support and documentation.
