"""Rutas del módulo Pedidos."""

from django.urls import path

from .views import PedidoCreateView

urlpatterns = [
    path("api/pedidos/", PedidoCreateView.as_view(), name="pedido-create"),
]
