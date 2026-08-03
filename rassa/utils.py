"""Utilidades compartidas del módulo rassa."""


def nombre_completo(usuario):
    """Retorna el nombre completo de un usuario a partir de su Persona.

    Usado por múltiples serializers (pagos, liquidaciones, etc.).
    """
    if usuario and getattr(usuario, "fk_persona_id", None):
        p = usuario.fk_persona
        return f"{p.nombre} {p.apellido_paterno}".strip()
    return None
"""Utilidades compartidas del proyecto."""

from datetime import datetime

from rest_framework.exceptions import ValidationError


def parse_date_param(raw, param_name):
    """Valida y convierte un parámetro de fecha a ``date``; lanza 400 si es inválido."""
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as err:
        raise ValidationError({param_name: f"{param_name} debe tener formato YYYY-MM-DD. Recibido: '{raw}'."}) from err
