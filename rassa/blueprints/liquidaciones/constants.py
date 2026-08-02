"""Constantes del módulo de Liquidaciones."""

from decimal import Decimal

COMISION_RASSA = Decimal("0.10")

ESTADO_PENDIENTE = "pendiente"
ESTADO_PARCIAL = "parcial"
ESTADO_PAGADA = "pagada"

ESTADOS_ACTIVOS = [ESTADO_PENDIENTE, ESTADO_PARCIAL]

MSG_LIQUIDACION_DUPLICADA = "Ya existe la liquidación #{id} para ese agricultor y periodo."
