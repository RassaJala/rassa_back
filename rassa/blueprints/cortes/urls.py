"""Configuración de rutas para el módulo de Cortes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CorteViewSet

router = DefaultRouter()
router.register(r"cortes", CorteViewSet, basename="corte")

urlpatterns = [
    path("api/", include(router.urls)),
]
