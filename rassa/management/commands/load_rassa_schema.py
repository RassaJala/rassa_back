"""Django management command to load rassa_jala.sql schema.

Executes db/rassa_jala.sql (32 tables + seeders) via Django's database
connection, statement by statement, wrapped in a controlled transaction.

Flags:
  --reset    Drop all existing tables before loading (fresh start).
  --dry-run  Execute in a transaction that always rolls back (validation).

Idempotent: re-running without --reset skips duplicate tables/data gracefully.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

# ---------------------------------------------------------------------------
# PostgreSQL-specific error classes (available only with psycopg2)
# ---------------------------------------------------------------------------
try:
    from psycopg2.errors import DuplicateTable, UniqueViolation  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover — SQLite environments
    DuplicateTable = None  # type: ignore[assignment,misc]
    UniqueViolation = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# SQL parsing
# ---------------------------------------------------------------------------


def _parse_sql(sql_text: str) -> list[tuple[int, str]]:
    """Parse raw SQL text into list of (line_number, statement) tuples.

    Strips BEGIN/COMMIT wrapper, removes comment-only and empty lines
    between statements, splits on semicolons. Inline comments within
    multi-line statements are preserved (PostgreSQL treats them as valid).

    Args:
        sql_text: Raw SQL file content.

    Returns:
        List of (original_line_number, statement_body) tuples in order.
    """
    lines = sql_text.split("\n")
    statements: list[tuple[int, str]] = []
    current_lines: list[str] = []
    start_line: int | None = None

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Skip BEGIN; / COMMIT; wrapper at file level
        if stripped.upper() in ("BEGIN;", "COMMIT;"):
            continue

        if start_line is None:
            # We are BETWEEN statements — skip comment-only lines and blanks
            if not stripped or stripped.startswith("--"):
                continue
            # Start of a new statement
            start_line = i
            current_lines = [line]
        else:
            # Already inside a statement — accumulate all lines (including inline comments)
            current_lines.append(line)

        # Statement boundary: the current line ends with a semicolon
        if stripped.endswith(";"):
            stmt_body = _clean_statement_body("\n".join(current_lines))
            if stmt_body:
                assert start_line is not None  # guaranteed by the if-block above
                statements.append((start_line, stmt_body))
            current_lines = []
            start_line = None

    # Handle final statement at EOF without trailing semicolon
    if start_line is not None and current_lines:
        stmt_body = _clean_statement_body("\n".join(current_lines))
        if stmt_body:
            statements.append((start_line, stmt_body))

    return statements


def _clean_statement_body(raw: str) -> str:
    """Remove trailing semicolon and surrounding whitespace."""
    body = raw.strip()
    if body.endswith(";"):
        body = body[:-1].strip()
    return body


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


def _is_idempotent_error(exc: Exception) -> bool:
    """Check whether an exception comes from an idempotent re-run.

    Returns True for DuplicateTable, UniqueViolation (PostgreSQL) or
    equivalent SQLite errors (table/index already exists).
    """
    # PostgreSQL: check by error class
    if DuplicateTable is not None and isinstance(exc, DuplicateTable):
        return True
    if UniqueViolation is not None and isinstance(exc, UniqueViolation):
        return True

    # SQLite / generic fallback: check error message
    msg = str(exc).lower()
    idempotent_markers = (
        "already exists",
        "unique constraint",
        "duplicate table",
        "duplicate key",
    )
    return any(marker in msg for marker in idempotent_markers)


# ---------------------------------------------------------------------------
# Table extraction helper
# ---------------------------------------------------------------------------


def _extract_table_name(statement: str) -> str:
    """Extract a human-readable table name from a CREATE TABLE statement."""
    upper = statement.upper().replace("\n", " ")
    if "CREATE TABLE" not in upper:
        return ""
    # Get text after CREATE TABLE [IF NOT EXISTS]
    after = upper.split("CREATE TABLE", 1)[1].strip()
    if after.startswith("IF NOT EXISTS"):
        after = after.split("IF NOT EXISTS", 1)[1].strip()
    # First token is the table name (may include schema prefix)
    table_name = after.split()[0]
    # Remove trailing parenthesis if name + paren on same line
    table_name = table_name.rstrip("(")
    return table_name


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = (
        "Carga el esquema y seeders desde db/rassa_jala.sql. "
        "Usa --reset para recrear todas las tablas. "
        "Usa --dry-run para validar sin modificar la base de datos."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            dest="reset",
            default=False,
            help="Elimina todas las tablas existentes y las recrea desde cero.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            default=False,
            help="Ejecuta el SQL dentro de una transacción que siempre hace rollback "
            "(válida sintaxis sin modificar la base de datos).",
        )

    def handle(self, *args, **options):
        sql_path = Path(settings.BASE_DIR) / "db" / "rassa_jala.sql"

        if not sql_path.exists():
            raise CommandError(
                f"Archivo SQL no encontrado: {sql_path}\n"
                "Asegurate de que db/rassa_jala.sql existe en la raíz del proyecto."
            )

        self.stdout.write(f"Cargando esquema desde: {sql_path}")

        raw_sql = sql_path.read_text(encoding="utf-8")
        statements = _parse_sql(raw_sql)

        if not statements:
            self.stdout.write(self.style.WARNING("No se encontraron sentencias SQL para ejecutar."))
            return

        self.stdout.write(f"Sentencias detectadas: {len(statements)}")

        dry_run = options["dry_run"]
        reset = options["reset"]

        if dry_run:
            self.stdout.write(self.style.WARNING("MODO DRY-RUN: los cambios NO se guardarán."))
            self._execute_dry_run(statements, reset=reset)
        else:
            self._execute(statements, reset=reset)

    # ------------------------------------------------------------------
    # Execution helpers
    # ------------------------------------------------------------------

    def _execute(self, statements: list[tuple[int, str]], reset: bool = False) -> None:
        """Execute statements inside a single committed transaction."""
        with connection.cursor() as cursor:
            if reset:
                self._drop_all_tables(cursor)

            try:
                with transaction.atomic():
                    for line_no, stmt in statements:
                        self._execute_one(cursor, line_no, stmt)
            except Exception:
                self.stdout.write(self.style.ERROR("Transacción revertida (ROLLBACK)."))
                raise

        self.stdout.write(self.style.SUCCESS("Esquema cargado exitosamente."))

    def _execute_dry_run(self, statements: list[tuple[int, str]], reset: bool = False) -> None:
        """Execute statements inside a transaction that ALWAYS rolls back."""
        with connection.cursor() as cursor:
            try:
                with transaction.atomic():
                    if reset:
                        self._drop_all_tables(cursor)

                    for line_no, stmt in statements:
                        self._execute_one(cursor, line_no, stmt)

                    # Always roll back, even on success
                    transaction.set_rollback(True)
            except Exception:
                self.stdout.write(self.style.ERROR("Transacción revertida (ROLLBACK)."))
                raise

        self.stdout.write(self.style.SUCCESS("Validación dry-run completada (sin cambios permanentes)."))

    def _execute_one(self, cursor, line_no: int, stmt: str) -> None:
        """Execute a single statement with progress output and error handling."""
        label = self._progress_label(stmt)
        try:
            cursor.execute(stmt)
            if label:
                self.stdout.write(f"  {label}... ", ending="")
                self.stdout.write(self.style.SUCCESS("OK"))
        except Exception as exc:
            if _is_idempotent_error(exc):
                if label:
                    self.stdout.write(f"  {label}... ", ending="")
                self.stdout.write(self.style.WARNING("WARNING (ya existe, se omite)"))
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"ERROR en línea {line_no}: {exc}\n"
                        f"  Sentencia: {stmt[:120]}{'...' if len(stmt) > 120 else ''}"
                    )
                )
                raise

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _progress_label(stmt: str) -> str:
        """Create a human-readable progress label from a SQL statement."""
        upper = stmt.strip().upper().replace("\n", " ")
        if upper.startswith("CREATE TABLE"):
            name = _extract_table_name(stmt)
            return f"Creando tabla {name}" if name else "Creando tabla"
        if upper.startswith("INSERT INTO"):
            return "Insertando datos"
        if upper.startswith("ALTER TABLE"):
            return "Modificando tabla"
        if upper.startswith("CREATE INDEX"):
            return "Creando índice"
        return "Ejecutando sentencia"

    def _drop_all_tables(self, cursor) -> None:
        """Drop all user tables from the database.

        Uses database-appropriate introspection to find and drop tables.
        Django-managed tables (django_*, auth_*, etc.) are preserved to
        keep the migration system functioning.
        """
        vendor = connection.vendor
        if vendor == "postgresql":
            cursor.execute(
                "SELECT tablename FROM pg_catalog.pg_tables "
                "WHERE schemaname = 'public'"
            )
        else:
            # SQLite
            cursor.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                "AND name NOT LIKE 'django_%' AND name NOT LIKE 'auth_%'"
            )

        tables = [row[0] for row in cursor.fetchall()]
        if not tables:
            self.stdout.write("  No hay tablas para eliminar.")
            return

        self.stdout.write(f"  Eliminando {len(tables)} tabla(s) existente(s)...")
        for table in tables:
            if vendor == "postgresql":
                cursor.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
            else:
                cursor.execute(f'DROP TABLE IF EXISTS "{table}"')
            self.stdout.write(f"    {table} ... {self.style.SUCCESS('OK')}")
