"""Django system checks para validaciones de despliegue."""

from django.core.checks import Error, register

MIN_PG_VERSION = 150000  # PostgreSQL 15.0


@register(deploy=True)
def check_postgresql_version(app_configs, **kwargs):
    """Verifica que PostgreSQL >= 15 para soporte de UNIQUE NULLS DISTINCT.

    La migración 0018 usa ``nulls_distinct=True`` en el constraint
    ``unique_pago_per_pedido``, sintaxis introducida en PG 15.
    """
    from django.db import connection

    errors = []

    if connection.vendor == "postgresql":
        pg_version = getattr(connection, "pg_version", 0)
        if pg_version and pg_version < MIN_PG_VERSION:
            major = pg_version // 10000
            minor = (pg_version % 10000) // 100
            errors.append(
                Error(
                    f"PostgreSQL {major}.{minor} es menor que 15.0. "
                    "La migración 0018 (nulls_distinct=True) requiere PG >= 15. "
                    "El deploy fallará en servidores con PG < 15.",
                    hint="Actualizar PostgreSQL a >= 15 o revertir la migración 0018.",
                    obj="rassa.migrations.0018_pago_unique_pedido_allow_null_distinct",
                    id="rassa.E001",
                )
            )

    return errors
