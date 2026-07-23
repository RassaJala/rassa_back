"""Configuración de rutas para el módulo de Pedidos."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PedidoViewSet

router = DefaultRouter()
router.register(r"pedidos", PedidoViewSet, basename="pedido")

urlpatterns = [
    path("api/", include(router.urls)),
]
