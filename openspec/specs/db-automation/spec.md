# db-automation Specification

## Purpose

Management command `load_rassa_schema` automates PostgreSQL schema loading from `db/rassa_jala.sql` (32 tables + seeders). It replaces manual SQL import with idempotent, verifiable execution supporting reset, dry-run, and precise error reporting.

## Requirements

### Requirement: Schema Loading

The system MUST execute `db/rassa_jala.sql` via `psycopg2` cursor, wrapped in a single database transaction. If any statement fails, the transaction MUST roll back completely.

#### Scenario: Successful first load

- GIVEN PostgreSQL is running and `rassa` database exists
- WHEN `python manage.py load_rassa_schema` is invoked
- THEN all 32 tables and seeders are created
- AND the command exits with code 0
- AND `dbshell` shows seed data (12 users, 20 products, 10 orders)

#### Scenario: Partial failure rolls back

- GIVEN the SQL file contains a syntax error at line 47
- WHEN `load_rassa_schema` processes line 47
- THEN the entire transaction is rolled back
- AND the command exits with a non-zero code
- AND the error message includes line number and the failing statement text

### Requirement: Reset Flag

The command MUST support `--reset` to drop and recreate all schema objects before loading.

#### Scenario: Reset drops existing tables

- GIVEN tables from a previous run exist in the database
- WHEN `python manage.py load_rassa_schema --reset` is invoked
- THEN all existing tables are dropped first
- AND then all 32 tables are recreated with fresh seed data
- AND the command exits with code 0

#### Scenario: Reset on empty database

- GIVEN the database has no tables
- WHEN `--reset` is used
- THEN the command proceeds without errors (DROP IF EXISTS is safe)
- AND tables are created normally

### Requirement: Dry-Run Validation

The command MUST support `--dry-run` to validate SQL syntax and connection without executing statements against the database.

#### Scenario: Dry-run validates without modifying

- GIVEN the SQL file is syntactically valid
- WHEN `python manage.py load_rassa_schema --dry-run` is invoked
- THEN no tables are created in the database
- AND the command reports "Validation successful" or equivalent
- AND exits with code 0

#### Scenario: Dry-run catches syntax errors

- GIVEN the SQL file contains an invalid statement
- WHEN `--dry-run` is used
- THEN the command reports the exact error and its line number
- AND exits with a non-zero code
- AND no database changes are made

### Requirement: Idempotent Execution

The command MUST be safe to run multiple times without `--reset`. It SHOULD NOT fail on pre-existing tables.

#### Scenario: Re-running without reset

- GIVEN tables already exist from a prior load
- WHEN `load_rassa_schema` runs again without `--reset`
- THEN the command completes without errors (e.g., using IF NOT EXISTS semantics)
- AND seed data is not duplicated (idempotent inserts)
