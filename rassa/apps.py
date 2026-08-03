"""Configuración de la app Rassa.

Define el AppConfig para la aplicación principal del proyecto,
que contiene los 32 modelos del dominio de negocio.
"""

from django.apps import AppConfig


class RassaConfig(AppConfig):
    """Configuración de la app Rassa.

    Attributes:
        default_auto_field: Tipo de campo auto-incremental por defecto.
        name: Nombre completo de la app (rassa).
        verbose_name: Nombre legible para el admin panel.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "rassa"
    verbose_name = "Rassa - Sistema de Gestión Agrícola"

    def ready(self):
        import rassa.checks  # noqa: F401 — registra system checks de postgresql >= 15
        import rassa.blueprints.chat.signals  # noqa: F401 — registra signal rename familia→chat
        import rassa.signals  # noqa: F401 — registra signals de historial de estados
