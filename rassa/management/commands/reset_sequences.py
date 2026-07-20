"""Django management command para resincronizar secuencias de PostgreSQL.

Después de cargar datos de prueba con INSERT o fixtures, las secuencias
autoincrementales de PostgreSQL quedan desfasadas respecto al máximo ID
existente. Esto causa errores como:

    IntegrityError: llave duplicada viola restricción de unicidad

Ejecuta: python manage.py reset_sequences
"""

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Resincroniza las secuencias de PostgreSQL con el máximo ID de cada tabla."

    def handle(self, *args, **options):
        tables = [
            "auth_user",
            "categoria_producto",
            "conversacion",
            "corte",
            "decision_merma",
            "detalle_pedido",
            "documento",
            "estado_pedido",
            "familia",
            "familia_usuario",
            "historial_estado_pedido",
            "integrantes",
            "limite_cliente",
            "localidad",
            "logs",
            "mensaje",
            "mensajes_documentos",
            "merma",
            "municipio",
            "pago",
            "pedido_cabecera",
            "persona",
            "producto",
            "producto_imagen",
            "producto_semanal",
            "publicacion_semanal",
            "recibo",
            "recoleccion",
            "roles",
            "tipo_pago",
            "unidad",
            "usuario",
        ]

        reset_statements = []
        with connection.cursor() as cursor:
            for table in tables:
                try:
                    # Check if the table exists and has a serial / identity primary key column
                    cursor.execute(
                        """
                        SELECT a.attname
                        FROM pg_index i
                        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                        WHERE i.indrelid = %s::regclass
                          AND i.indisprimary
                          AND a.atttypid = 'integer'::regtype
                        LIMIT 1;
                        """,
                        [table],
                    )
                except Exception as err:
                    self.stdout.write(self.style.WARNING(f"Skipping {table}: {err}"))
                    continue

                row = cursor.fetchone()
                if not row:
                    continue

                pk_column = row[0]
                sequence_name = f"{table}_{pk_column}_seq"

                # Check if the sequence exists
                cursor.execute(
                    "SELECT 1 FROM pg_class WHERE relkind = 'S' AND relname = %s",
                    [sequence_name],
                )
                if not cursor.fetchone():
                    continue

                reset_statements.append(
                    f"SELECT setval('{sequence_name}', COALESCE((SELECT MAX({pk_column}) FROM {table}), 1));"
                )

            for sql in reset_statements:
                cursor.execute(sql)
                self.stdout.write(self.style.SUCCESS(sql))

        self.stdout.write(self.style.SUCCESS(f"\n{len(reset_statements)} secuencias resincronizadas correctamente."))
