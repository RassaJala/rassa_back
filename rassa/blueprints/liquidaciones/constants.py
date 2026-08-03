"""Constantes del módulo de Liquidaciones."""

from decimal import Decimal

COMISION_RASSA = Decimal("0.10")

ESTADO_PENDIENTE = "pendiente"
ESTADO_PAGADA = "pagada"
ESTADOS_ACTIVOS = ["pendiente", "parcial"]
ESTADO_PEDIDO_ENTREGADO = "entregado"

# Estado `parcial` está en ESTADO_CHOICES del modelo (Liquidacion) pero
# ninguna ruta del backend lo produce hoy (calcular siempre crea
# `pendiente`, marcar_pagada solo acepta `pendiente`/`parcial` → `pagada`).
# Se conserva en el modelo por compatibilidad con la tabla SQL existente.

MSG_LIQUIDACION_DUPLICADA = "Ya existe la liquidación #{id} para ese agricultor y periodo."
