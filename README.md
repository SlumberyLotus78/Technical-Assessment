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

Obtain a [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html) and a [Banco de México API token](https://www.banxico.org.mx/SieAPIRest/service/v1/token) before querying the sources.

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

Replace `admin` with the configured project login role. Database creation requires an administrator with the appropriate privileges; see [CREATE DATABASE](https://www.postgresql.org/docs/18/sql-createdatabase.html).

The project account must be able to connect to the database, create the `core`, `mart`, and `ops` schemas, and own the objects it creates. Using the project database owner provides these permissions in the standard setup. See [PostgreSQL privileges](https://www.postgresql.org/docs/18/ddl-priv.html).

If you choose another database name, use that same name in `DATABASE_URL`.

### 3. Configure Private Credentials

Create the local configuration file if it does not exist:

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
```

Fill in `.env` with your credentials:

```dotenv
FRED_API_KEY=YOUR_FRED_API_KEY
BANXICO_TOKEN=YOUR_BANXICO_TOKEN
DATABASE_URL=postgresql://admin:YOUR_PASSWORD@localhost:5432/fred_banxico
```

Use your actual host, port, login role, password, and database name. Reserved characters in a URL password must be percent-encoded. Process environment variables take precedence over values in `.env`.

The configuration template is tracked in Git. The private `.env` file is excluded through `.gitignore`.

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

The [PostgreSQL guide](docs/GUIA_POSTGRESQL_ES.md) describes connection formats, permissions, version checks, and schema verification.

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

The sample contains three months for each monthly grain series and one month for daily FIX observations, ending in the same month. To select the final month explicitly, use `--month YYYY-MM`; the command checks its availability before querying observations.

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

The [Silver preparation guide](docs/GUIA_PERSISTENCIA_SILVER_ES.md) describes record validation, capture integrity, persistence functions, and transaction boundaries.


## Tests

Run the test suite:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

Tests use fixtures, archived captures, and simulated API responses. PostgreSQL integration tests require `TEST_DATABASE_URL` pointing to a dedicated database whose name begins with `grain_test_`, using an account with permission to create databases. Each integration case creates and removes its own `grain_test_<uuid>` database

Integration tests are skipped when `TEST_DATABASE_URL` is not set. Their connection is independent of the project database configured in `.env`. See the [PostgreSQL guide](docs/GUIA_POSTGRESQL_ES.md) for integration-test requirements.

## Project Structure

```text
grain_pipeline/
    clients/          Authenticated HTTP communication
    common/           Configuration and shared date utilities
    extraction/       Source captures and sample extraction
    persistence/      PostgreSQL connections, schema setup, and catalog
        sql/          Versioned SQL resources
    quality/          Numeric interpretation and data-quality profiling
    sources/          Series catalog, contracts, and source queries
tests/                Unit and PostgreSQL integration tests
docs/                 Technical documentation and evidence
data/                 Local generated captures and reports
```

## Documentation

- [Data model](docs/MODELO_DATOS_ES.md)
- [Data dictionary](docs/DICCIONARIO_DATOS_ES.md)
- [Data-quality rules](docs/REGLAS_CALIDAD_ES.md)
- [PostgreSQL setup and command guide](docs/GUIA_POSTGRESQL_ES.md)
- [Initial data profiling](docs/Perfilamiento_inicial.md)
- [Implementation process](docs/Implementación_proceso.md)

Supporting technical documents are written in Spanish.

## Acknowledgments

Source data is provided by FRED and Banco de México. AI assistance was used for coding support and documentation.
