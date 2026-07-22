# AGENTS.md — rassa_back

## Project

Django 5 + DRF REST API for a mobile e-commerce app (farmers selling produce directly).
Python 3.12+ / PostgreSQL / JWT auth (SimpleJWT). Spanish-language codebase and user-facing messages.

## Commands

```bash
# Full setup (creates venv, installs deps, configures DB, runs migrations + seed)
bash setup.sh          # Linux/macOS/Git Bash/WSL
.\setup.ps1            # Windows PowerShell

# Start backend (runs ALL tests first; server only starts if tests pass)
bash start.sh          # Linux/macOS/Git Bash/WSL
.\start.ps1            # Windows PowerShell

# Start without tests (emergencies only)
bash start.sh --skip

# Run tests only (no server)
bash start.sh --test
bash start.sh --test --verbose   # verbosity 3

# Lint / format (ruff)
ruff check .
ruff format .
ruff check --fix .      # auto-fix
ruff format .           # auto-format

# Django checks
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run   # verify no pending migrations

# Single test file
python -m pytest rassa/tests/test_<name>.py -v

# Seed data
python manage.py seed_rassa_data          # load test data
python manage.py seed_rassa_data --clear  # wipe + reload
```

## Verification order

`lint → typecheck (manage.py check) → tests → start`

The `start.sh` script enforces: tests must pass before the server starts.

## Code structure

- **`rassa/`** — main Django project and the primary app
  - `models.py` — all 32 domain models (single file, not split per app)
  - `views.py` — main API views (catalogos, municipios, localidades, auth)
  - `admin_views.py` — admin-only ViewSets
  - `auth_serializers.py` / `auth_views.py` — JWT auth
  - `permissions/role_permissions.py` — RBAC: IsAdmin, IsAgricultor, IsVendedor, IsCliente, IsOwnerOrAdmin, etc.
  - `urls.py` — central router; includes blueprint URL modules
  - `blueprints/` — feature modules (publicacion, chat, familias), each with views/serializers/urls
  - `tests/` — all tests live here (flat, not per-blueprint)
  - `management/commands/seed_rassa_data.py` — seeder command
- **`apps/`** — legacy/placeholder; real code is in `rassa/`
- **`logs/`** — activity logging app (middleware + models + views)
- **`bruno/`** — Bruno API collection for manual endpoint testing
- **`docs/`** — architecture docs, Bruno guides
- **`scripts/`** — test helper scripts

## Conventions

- **Linter**: ruff (line-length=120, target py312). Rules: E, W, F, I, B, UP.
- **Formatter**: ruff format, double quotes, space indentation.
- **Pre-commit**: ruff (with `--fix`), trailing-whitespace, end-of-file-fixer, check-yaml, no large files (>500KB).
- **Tests**: pytest with pytest-django (`DJANGO_SETTINGS_MODULE=rassa.settings`). Pattern: `test_*.py` / `tests.py`. Verbose short tracebacks by default.
- **Branch naming**: `tipo/descripcion-corta-en-ingles` (e.g. `feat/user-registration`). Max 4 words, lowercase, no issue numbers.
- **Commits**: Conventional Commits — `tipo(alcance): description`. Imperative mood. One logical change per commit.
- **Serializers**: validation error messages must be in **Spanish**.
- **Error messages to users**: always in Spanish.
- **RBAC**: endpoints must specify explicit permission classes from `rassa/permissions/role_permissions.py`.
- **New endpoints**: must include corresponding Bruno `.bru` files in `bruno/{modulo}/`.
- **Migrations**: always include generated migrations in PR; never edit existing ones.
- **Settings**: uses `python-decouple` for env vars (not `os.environ` directly). Config loaded from `.env`.
- **Locale**: `es-ar` / `America/Argentina/Buenos_Aires`.

## Gotchas

- `start.sh` is the canonical way to start the dev server; bare `python manage.py runserver` skips test verification.
- `rassa/models.py` contains all 32 models in one file — expect it to be large.
- PR-GUIDE-BACKEND.md references `flake8` for lint but the project actually uses **ruff**.
- The `apps/` directory is mostly empty; the real app code lives under `rassa/` and `rassa/blueprints/`.
- JWT access tokens expire in 2 hours; refresh tokens in 7 days.
- `manage.py check --deploy` may show non-critical warnings (e.g. HTTPS settings) — these are expected in dev.
