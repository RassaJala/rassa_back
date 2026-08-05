"""Configuración de rutas para el módulo de Liquidaciones."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import LiquidacionViewSet

router = DefaultRouter()
router.register(r"liquidaciones", LiquidacionViewSet, basename="liquidacion")

urlpatterns = [
    path("api/", include(router.urls)),
]
