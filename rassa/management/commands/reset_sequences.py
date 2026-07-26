"""Django management command para resincronizar secuencias de PostgreSQL.

Después de cargar datos de prueba con INSERT o fixtures, las secuencias
autoincrementales de PostgreSQL quedan desfasadas respecto al máximo ID
existente. Esto causa errores como:

    IntegrityError: llave duplicada viola restricción de unicidad

Ejecuta:
    python manage.py reset_sequences
    python manage.py reset_sequences --database=default --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import connections


class Command(BaseCommand):
    help = "Resincroniza las secuencias de PostgreSQL con el máximo ID de cada tabla."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default="default",
            help="Nombre de la conexión de base de datos a usar (default: default).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra las sentencias SQL sin ejecutarlas.",
        )

    def handle(self, *args, **options):
        database = options["database"]
        dry_run = options["dry_run"]
        connection = connections[database]

        if connection.vendor != "postgresql":
            self.stderr.write(self.style.ERROR("Este comando solo funciona con PostgreSQL."))
            return

        tables = connection.introspection.table_names()
        reset_statements = []

        with connection.cursor() as cursor:
            for table in tables:
                try:
                    # Check if the table has a serial / identity primary key column
                    # Accept both integer (32-bit) and bigint (64-bit) PKs.
                    # Django's BigAutoField (the default since 3.2, used by this project)
                    # maps to bigint — filtering only integer would silently skip every table.
                    cursor.execute(
                        """
                        SELECT a.attname
                        FROM pg_index i
                        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                        WHERE i.indrelid = %s::regclass
                          AND i.indisprimary
                          AND a.atttypid IN ('integer'::regtype, 'bigint'::regtype)
                        LIMIT 1;
                        """,
                        [table],
                    )
                except Exception as err:
                    # ponytail: broad catch is intentional — this is a dev/ops tool that
                    # must keep iterating tables even if one fails ( PermissionDenied on a
                    # view, schema mismatch, missing sequence ). Each failure is logged;
                    # narrowing to specific DB errors would silently skip other recoverable
                    # cases and defeat the "reset everything we can" contract.
                    self.stdout.write(self.style.WARNING(f"Skipping {table}: {err}"))
                    continue

                row = cursor.fetchone()
                if not row:
                    continue

                pk_column = row[0]
                sequence_name = f"{table}_{pk_column}_seq"

                # Check if the sequence exists.
                # ponytail: relkind='S' assumes legacy serial/sequence naming; Django 5.x
                # may use IDENTITY columns (pg_identity) which won't match here and would
                # need updating to query pg_identity instead.
                cursor.execute(
                    "SELECT 1 FROM pg_class WHERE relkind = 'S' AND relname = %s",
                    [sequence_name],
                )
                if not cursor.fetchone():
                    continue

                q_table = connection.ops.quote_name(table)
                q_pk = connection.ops.quote_name(pk_column)
                q_seq = connection.ops.quote_name(sequence_name)
                reset_statements.append(f"SELECT setval({q_seq}, COALESCE((SELECT MAX({q_pk}) FROM {q_table}), 1));")

            if dry_run:
                self.stdout.write(self.style.NOTICE("Dry-run. Sentencias que se ejecutarían:"))
            else:
                self.stdout.write(self.style.NOTICE("Ejecutando reset de secuencias..."))

            for sql in reset_statements:
                if dry_run:
                    self.stdout.write(sql)
                else:
                    cursor.execute(sql)
                    self.stdout.write(self.style.SUCCESS(sql))

        action = "requerirían reset" if dry_run else "resincronizadas"
        summary_style = self.style.NOTICE if dry_run else self.style.SUCCESS
        self.stdout.write(summary_style(f"\n{len(reset_statements)} secuencias {action}"))
