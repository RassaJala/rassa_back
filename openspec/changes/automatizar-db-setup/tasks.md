# Tasks: Automatizar Setup de Base de Datos

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~870 (300+ deletions from 4 apps + ~570 new/modified) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (cleanup+auth) → PR 2 (command+tests) → PR 3 (setup.sh+docs) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Foundation + auth extraction + settings/urls cleanup (~120 lines) | PR 1 | Base: main. Deletes 4 apps. Extract auth first. |
| 2 | load_rassa_schema command + tests (~350 lines) | PR 2 | Base: PR 1. Independent after auth is extracted. |
| 3 | setup.sh orchestration + docs + .env (~400 lines) | PR 3 | Base: PR 2. Depends on command existing. |

## Phase 1: Foundation (Directory & File Moves)

- [x] 1.1 Create `db/` directory. Move `rassa_jala.sql` → `db/rassa_jala.sql`. Create `db/migrations_archive/` and archive old migration files from `apps/*/migrations/` there.
- [x] 1.2 Create `rassa/management/__init__.py` and `rassa/management/commands/__init__.py` (empty package files for Django command discovery).
- [x] 1.3 Create `.env.template` with documented placeholders: `SECRET_KEY=changeme`, `DEBUG=True`, `DATABASE_URL=postgres://postgres:postgres@localhost:5432/rassa`.
- [x] 1.4 Add `setup.log` and `.setup_state` to `.gitignore`.

## Phase 2: Auth Extraction (from `apps/accounts/` to `rassa/`)

- [x] 2.1 Create `rassa/auth_serializers.py`. Extract `CustomTokenObtainPairSerializer` from `apps/accounts/serializers.py`, changing import from `apps.accounts.models.User` to `django.contrib.auth.models.User`. Preserve Spanish error messages.
- [x] 2.2 Create `rassa/auth_views.py`. Extract `CustomTokenObtainPairView` from `apps/accounts/views.py`, importing serializer from `rassa.auth_serializers`.

## Phase 3: Settings & URLs — Remove Obsolete Apps

- [x] 3.1 Modify `rassa/settings.py`: remove `LOCAL_APPS` list and its reference from `INSTALLED_APPS`. Remove `AUTH_USER_MODEL` (fall back to default Django `User`). Add `"rassa"` to `INSTALLED_APPS` for management command discovery.
- [x] 3.2 Modify `rassa/urls.py`: remove `apps.accounts`, `apps.products`, `apps.orders`, `apps.categories` imports and url patterns. Change `CustomTokenObtainPairView` import to `rassa.auth_views`. Verify `python manage.py check` passes.
- [x] 3.3 Delete `apps/accounts/`, `apps/products/`, `apps/orders/`, `apps/categories/` directories entirely.

## Phase 4: Management Command — `load_rassa_schema`

- [x] 4.1 Create `rassa/management/commands/load_rassa_schema.py`. Implement `BaseCommand` with `--reset` (DROP all tables via information_schema then recreate) and `--dry-run` (execute in transaction that always rolls back). Parse SQL statement-by-statement (strip BEGIN/COMMIT, split by `;`, strip comments). Execute under controlled transaction with per-statement progress output. Catch `DuplicateTable`/`UniqueViolation` → WARNING for idempotent re-runs. On other errors, ROLLBACK + report line number + failing statement.

## Phase 5: Tests — Management Command

- [x] 5.1 Create `rassa/tests/test_load_rassa_schema.py`. Write unit tests for `_parse_sql()` (comment stripping, statement splitting, empty line filtering) using inline SQL strings.
- [x] 5.2 Add integration tests: `--dry-run` validates real SQL without side effects; `--reset` drops + recreates 32 tables; re-run without `--reset` is idempotent. Use `connection.introspection.table_names()` to verify table count. Verify seed data counts (12 users, 20 products, 10 orders) via direct SQL queries.
- [x] 5.3 Run `python manage.py test rassa.tests.test_load_rassa_schema` — all tests must pass.

## Phase 6: Orchestration Script — `setup.sh`

- [x] 6.1 Create `setup.sh` with `set -Eeuo pipefail`, `trap ERR`, OS detection (Linux/macOS), color output, and tee logging to `setup.log`. Implement modular functions: `phase_1_python()` detects Python versions with three-option menu, `phase_2_venv()` creates/recreates venv, `phase_3_pip()` installs with per-package verification, `phase_4_postgres()` checks `pg_isready` + `createdb rassa`, `phase_5_env()` copies `.env.template` → `.env` + validates vars, `phase_6_migrate()` runs `migrate`, `phase_7_schema()` calls `load_rassa_schema`, `phase_8_verify()` runs `check --deploy` + brief `runserver`. State tracking via `.setup_state` (skip completed phases on re-run). Each phase reports success/failure with error details.
- [x] 6.2 Windows cross-platform: `_detect_os()` detecta 4 SO (linux, macos, windows-gitbash, windows-wsl). Python detection usa `where` en Git Bash. Venv activation maneja `venv/Scripts/activate`. PostgreSQL detecta `C:\Program Files\PostgreSQL\{14-17}\bin`. Crear `setup.ps1` para PowerShell nativo (8 fases con `Write-Host`, `$LASTEXITCODE`, `try/catch`).

## Phase 7: Documentation & Final Wiring

- [x] 7.1 Modify `.env`: change `DATABASE_URL` to `postgres://postgres:postgres@localhost:5432/rassa`.
- [x] 7.2 Update `README.md`: replace manual onboarding steps with `git clone` → `bash setup.sh` → ready. Document `load_rassa_schema --reset` and `--dry-run` usage.
- [x] 7.3 Run `bash setup.sh` end-to-end on a clean environment. Verify: `python manage.py check --deploy` passes, `runserver` boots at `http://localhost:8000/api/`, `dbshell` shows seed data.
