# dev-environment-setup Specification

## Purpose

Single-command (`bash setup.sh`) orchestrates the complete development environment: Python detection, virtual environment, dependencies, PostgreSQL, environment variables, Django migrations, schema loading, and final verification. Each phase is independently idempotent with clear error reporting.

## Requirements

### Requirement: Python Detection and Selection

The script MUST detect installed Python versions via `which` / `command -v`. If multiple versions exist, it SHALL present three options: choose one manually, delete all and install latest, or cancel. If only an old-but-compatible version (≥3.11) exists, it SHALL ask to upgrade. If no compatible Python is found, it MUST display OS-specific install instructions and exit.

#### Scenario: Single compatible Python found

- GIVEN Python 3.12 is the only installed version
- WHEN setup.sh runs Phase 1
- THEN it proceeds automatically without prompting

#### Scenario: Multiple Python versions found

- GIVEN Python 3.11, 3.12, and 3.14 are installed
- WHEN setup.sh runs Phase 1
- THEN it lists all versions with detected paths
- AND presents the three-option menu
- AND waits for user input before proceeding

#### Scenario: Old but compatible Python

- GIVEN only Python 3.11 is installed
- WHEN setup.sh runs Phase 1
- THEN it warns "version 3.11 found, consider upgrading"
- AND asks whether to proceed or abort

#### Scenario: No Python installed

- GIVEN no Python executable is found on PATH
- WHEN setup.sh runs Phase 1
- THEN it displays OS-specific instructions (apt install python3.12 / brew install python@3.12)
- AND exits with a non-zero code

### Requirement: Virtual Environment Management

The script MUST create a `venv/` directory. If one already exists, it SHALL ask whether to recreate or reuse it.

#### Scenario: First run, no venv

- GIVEN `venv/` does not exist
- WHEN Phase 2 executes
- THEN `python -m venv venv` is run
- AND the prompt is activated for subsequent phases

#### Scenario: Pre-existing venv

- GIVEN `venv/` already exists from a previous run
- WHEN Phase 2 executes
- THEN the user is asked "venv exists. Recreate? [y/N]"
- AND on 'y', the old venv is removed and recreated

### Requirement: Dependency Installation

The script MUST run `pip install -r requirements.txt` inside the venv and verify each package. On failure, it SHALL report the failing package name and pip error message, then exit.

#### Scenario: All packages install successfully

- GIVEN venv is active and requirements.txt is present
- WHEN Phase 3 executes
- THEN pip installs all packages
- AND each package name is verified and reported as "OK"

#### Scenario: Single package fails

- GIVEN `psycopg2-binary` fails to compile (missing pg_config)
- WHEN Phase 3 processes that package
- THEN the script reports "FAILED: psycopg2-binary — [pip error details]"
- AND exits without proceeding to Phase 4

### Requirement: PostgreSQL Detection and Database Creation

The script MUST verify PostgreSQL is installed and running via `pg_isready`. If missing, it SHALL display OS-specific install instructions. If running, it MUST create the `rassa` database if it does not exist.

#### Scenario: PostgreSQL installed and running

- GIVEN PostgreSQL is running and accepting connections
- WHEN Phase 4 executes
- THEN it creates the `rassa` database via `createdb` (or reports it already exists)
- AND proceeds to Phase 5

#### Scenario: PostgreSQL not installed

- GIVEN `pg_isready` is not found on PATH
- WHEN Phase 4 executes
- THEN it displays OS-specific instructions (apt install postgresql / brew install postgresql@16)
- AND exits with instructions to re-run setup.sh after installing

### Requirement: Environment Variables Configuration

The script MUST create `.env` from `.env.template` if `.env` does not exist. It SHALL validate that `SECRET_KEY` and `DATABASE_URL` are present. Missing values SHALL trigger a warning but use safe defaults.

#### Scenario: No .env file exists

- GIVEN `.env` does not exist but `.env.template` does
- WHEN Phase 5 executes
- THEN `.env` is created from the template
- AND required variables are validated

#### Scenario: .env exists but missing DATABASE_URL

- GIVEN `.env` exists without `DATABASE_URL`
- WHEN Phase 5 validates
- THEN a warning is shown: "DATABASE_URL missing, using postgres://localhost/rassa"
- AND the script continues

### Requirement: Django Migration Execution

The script MUST run `python manage.py migrate` for Django system tables (auth, sessions, admin, contenttypes).

#### Scenario: Migrations succeed

- GIVEN the database and dependencies are ready
- WHEN Phase 6 executes
- THEN Django applies all pending migrations
- AND reports the number of migrations applied

#### Scenario: Migration fails

- GIVEN a migration file is corrupted or the database is unreachable
- WHEN Phase 6 executes
- THEN the script reports the migration error and exact traceback snippet
- AND exits without proceeding

### Requirement: Schema Loading via Management Command

The script MUST delegate schema loading to `python manage.py load_rassa_schema` as Phase 7.

#### Scenario: Schema loads successfully

- GIVEN migrations are applied
- WHEN Phase 7 executes `load_rassa_schema`
- THEN all 32 tables and seeders are created
- AND the phase reports success

#### Scenario: Schema load fails

- GIVEN the SQL file has a syntax error
- WHEN Phase 7 runs
- THEN the script reports the failing SQL statement line
- AND exits, reporting "Phase 7 (schema load) failed"

### Requirement: Final Verification

The script MUST run `python manage.py check --deploy` in Phase 8. Optionally, it MAY attempt a brief `runserver` start to verify the app boots. It SHALL report "Setup complete — project ready" on success, or the exact failure reason.

#### Scenario: All checks pass

- GIVEN all prior phases completed successfully
- WHEN Phase 8 executes `check --deploy`
- THEN zero deployment warnings are reported
- AND the script reports "Setup complete — project ready"
- AND exits with code 0

#### Scenario: Deploy check reveals issues

- GIVEN `SECRET_KEY` is set to a default value
- WHEN `check --deploy` runs
- THEN the warning is surfaced in the final report
- BUT the script still reports completion (non-fatal warning)

### Requirement: Phase Error Handling and Idempotency

The script MUST track which phase is executing. On failure, it SHALL report: the phase number, the exact error, and a suggested fix. Each phase MUST be safe to re-run (idempotent or state-detecting).

#### Scenario: Script fails mid-execution

- GIVEN Phase 3 (pip install) fails
- WHEN the user re-runs setup.sh
- THEN Phases 1 and 2 detect existing state and skip or prompt minimally
- AND Phase 3 retries from scratch

#### Scenario: OS detection at startup

- GIVEN the script runs on macOS
- WHEN it needs to display install instructions
- THEN it uses `brew` commands, not `apt`
- WHEN it runs on Ubuntu/Debian
- THEN it uses `apt` commands, not `brew`
