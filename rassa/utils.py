"""Utilidades compartidas del proyecto."""

from datetime import datetime

from rest_framework.exceptions import ValidationError


def parse_date_param(raw, param_name):
    """Valida y convierte un parámetro de fecha a ``date``; lanza 400 si es inválido."""
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as err:
        raise ValidationError({param_name: f"{param_name} debe tener formato YYYY-MM-DD. Recibido: '{raw}'."}) from err
