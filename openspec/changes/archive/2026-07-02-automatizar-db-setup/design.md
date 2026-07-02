# Design: Automatizar Setup de Base de Datos

## Technical Approach

Single-command dev setup via `bash setup.sh` orchestrating 8 sequential phases: Python detection → venv → pip → PostgreSQL → .env → `migrate` → `load_rassa_schema` → verify. A custom Django management command `load_rassa_schema` executes `db/rassa_jala.sql` (32 tables + seeders wrapped in `BEGIN/COMMIT`) via psycopg2, statement-by-statement, replacing 4 obsolete Django model apps. Bash state tracking (`.setup_state`) makes re-runs skip completed phases.

## Architecture Decisions

| Decision | Options | Chosen | Rationale |
|----------|---------|--------|-----------|
| Management command location | A: `rassa/management/commands/` (+ add `rassa` to `INSTALLED_APPS`); B: New `db_loader` app | **A** | Project-level commands in config package. No extra app overhead. Standard Django pattern for project-scoped commands. |
| SQL execution | A: Execute entire file as one string; B: Split by `;`, execute statement-by-statement | **B** | Enables per-statement progress output ("Creating table usuario... OK"), precise error line numbers, and controlled transaction wrapping independent of the file's own `BEGIN/COMMIT`. |
| Dry-run strategy | A: `EXPLAIN` each statement; B: Execute in a transaction that always rolls back | **B** | Executes real SQL against a live connection, catching syntax, type, and FK errors. Guarantees zero side effects via guaranteed `ROLLBACK`. |
| Idempotency (re-run without `--reset`) | A: Transform CREATE to `IF NOT EXISTS`; B: Catch `DuplicateTable`/`UniqueViolation`, log as warning, continue | **B** | Avoids modifying the SQL file. Catches known safe duplicates, logs them, and proceeds. Other errors still fail the command. |
| Auth after app deletion | A: Keep minimal `accounts` app; B: Remove `AUTH_USER_MODEL`, revert to default Django `User`, extract `CustomTokenObtainPairSerializer` to `rassa/` for Spanish error messages | **B** | Business users live in SQL table `usuario`. Django's built-in `User` handles admin access. Serializer moves to `rassa/auth_serializers.py` with import changed to `django.contrib.auth.models.User`. |

## Data Flow

```
setup.sh
  │
  ├─(1)── python3 detection → choose version → prompt if ≥2 found
  ├─(2)── venv/ (python3 -m venv)
  ├─(3)── pip install -r requirements.txt [per-package verify]
  ├─(4)── pg_isready? → OS install guide (apt/brew) → createdb rassa
  ├─(5)── .env from .env.template [validate required vars]
  ├─(6)── python manage.py migrate [auth, sessions, admin tables]
  ├─(7)── python manage.py load_rassa_schema
  │         │
  │         ├─ parse(db/rassa_jala.sql) → strip BEGIN/COMMIT → split by ;
  │         ├─ [if --reset] query information_schema → DROP CASCADE all tables
  │         ├─ BEGIN
  │         ├─ for each statement: cursor.execute() → stdout "OK" or catch+ROLLBACK+line#
  │         └─ COMMIT (or ROLLBACK if --dry-run)
  ├─(8)── python manage.py check --deploy
  └─(9)── python manage.py runserver [brief → kill after 3s]
```

Phase completion is tracked in `.setup_state` (key-value: `phase_1=done`). On re-run, completed phases are skipped. Removing `.setup_state` forces full re-run.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `setup.sh` | **Create** | Bash script: `set -Eeuo pipefail`, `trap ERR`, modular functions per phase, OS detection (Linux/macOS), color output (`\033[32m`/`\033[33m`/`\033[31m`), tee to `setup.log` |
| `.env.template` | **Create** | Documented template with placeholders: `SECRET_KEY=changeme`, `DEBUG=True`, `DATABASE_URL=postgres://postgres:postgres@localhost:5432/rassa` |
| `db/` | **Create** | Database artifacts directory |
| `rassa_jala.sql` → `db/rassa_jala.sql` | **Move** | Relocate to `db/`; also archive old Django migrations to `db/migrations_archive/` |
| `rassa/management/__init__.py` | **Create** | Django management package |
| `rassa/management/commands/__init__.py` | **Create** | Commands package |
| `rassa/management/commands/load_rassa_schema.py` | **Create** | `BaseCommand` with `--reset`, `--dry-run` flags. Parses SQL into `list[(line_no, statement)]`, executes under controlled transaction. Per-statement progress: `self.stdout.write(self.style.SUCCESS(...))`. |
| `rassa/auth_serializers.py` | **Create** | Extract `CustomTokenObtainPairSerializer` from `apps/accounts/serializers.py`. Change `from .models import User` → `from django.contrib.auth.models import User`. Spanish error messages preserved: "No existe una cuenta con este correo.", "Contraseña incorrecta." |
| `rassa/auth_views.py` | **Create** | Extract `CustomTokenObtainPairView` from `apps/accounts/views.py`. Imports serializer from `rassa.auth_serializers`. |
| `rassa/settings.py` | **Modify** | Remove `LOCAL_APPS` block + reference. Remove `AUTH_USER_MODEL`. Add `"rassa"` to `INSTALLED_APPS` for management command discovery. |
| `rassa/urls.py` | **Modify** | Remove `apps.accounts`, `apps.products`, `apps.orders`, `apps.categories` imports and url patterns. Change `CustomTokenObtainPairView` import from `apps.accounts.views` → `rassa.auth_views`. |
| `apps/accounts/` | **Delete** | Entire directory — `CustomTokenObtainPairSerializer` and `CustomTokenObtainPairView` were extracted to `rassa/` first. |
| `apps/products/` | **Delete** | Entire directory |
| `apps/orders/` | **Delete** | Entire directory |
| `apps/categories/` | **Delete** | Entire directory |
| `README.md` | **Modify** | Replace manual steps with: `git clone` → `bash setup.sh` → ready. Document `load_rassa_schema` usage. |
| `.env` | **Modify** | Default `DATABASE_URL=postgres://postgres:postgres@localhost:5432/rassa` |
| `.gitignore` | **Modify** | Add `setup.log`, `.setup_state` |

## Component Design: `load_rassa_schema`

```
rassa/management/commands/load_rassa_schema.py
 ┌──────────────────────────────────────────┐
 │ class Command(BaseCommand)               │
 │   add_arguments(): --reset, --dry-run     │
 │   handle():                              │
 │     sql = read(db/rassa_jala.sql)         │
 │     statements = _parse(sql)  # → list[tuple[int,str]] │
 │     if dry_run:                           │
 │       _execute_in_rollback(statements)     │
 │     else:                                 │
 │       _execute(statements, reset=reset)   │
 │                                           │
 │   _parse(sql: str):                       │
 │     strip BEGIN/COMMIT                    │
 │     split by ;                           │
 │     strip comments, filter empty          │
 │     yield (line_number, statement)        │
 │                                           │
 │   _execute(statements, reset):            │
 │     if reset: DROP ALL via info_schema    │
 │     BEGIN → per-stmt try/except →        │
 │       DuplicateTable/UniqueViolation →    │
 │         WARNING (idempotent)             │
 │       Other → ROLLBACK + line # error     │
 │     → COMMIT                              │
 └──────────────────────────────────────────┘
```

## Testing Strategy

| Layer | What | Tool |
|-------|------|------|
| Unit | `_parse_sql()`: comment stripping, statement splitting | Django `TestCase`, inline SQL strings |
| Unit | `setup.sh` phase functions | `bats-core` (bash testing framework) |
| Integration | `--dry-run` validates real SQL against test PostgreSQL | Django `TestCase` + live test DB |
| Integration | `--reset` drops + recreates; verify 32 tables via `connection.introspection.table_names()` | Django `TestCase` + live test DB |
| Integration | Re-run without `--reset` → idempotent (no errors on duplicate tables/rows) | Django `TestCase` + live test DB |

## Migration / Rollout

No data migration. Rollback: `git revert` restores deleted apps and settings. Old SQLite `.env` restored from git history.

## Open Questions

None — all technical decisions resolved by proposal + spec. Idempotency is handled at the Python level via error-class catching (`DuplicateTable`, `UniqueViolation` → WARNING, not ERROR).
