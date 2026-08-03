"""System checks personalizados para el proyecto Rassa."""

from django.core.checks import Warning as CheckWarning
from django.core.checks import register
from django.db import DatabaseError, connection


@register()
def check_postgresql_version(app_configs, **kwargs):
    """Verifica que la versión de PostgreSQL sea >= 15 en producción."""
    errors = []
    if connection.vendor == "postgresql":
        try:
            pg_version = connection.pg_version
            if pg_version is not None and pg_version < 150000:
                errors.append(
                    CheckWarning(
                        "La versión de PostgreSQL es inferior a la 15. "
                        "La restricción nulls_distinct=True requiere PostgreSQL 15 o superior.",
                        hint="Actualice PostgreSQL a la versión 15 o superior.",
                        id="rassa.W001",
                    )
                )
        except DatabaseError:
            # Si no se puede conectar a la BD durante el check (ej. en CI sin BD lista),
            # se ignora para no romper los comandos básicos.
            pass
    return errors
