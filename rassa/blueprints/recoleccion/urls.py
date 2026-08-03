"""Configuración de rutas para el módulo de Recolecciones."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import RecoleccionViewSet

router = DefaultRouter()
router.register(r"api/recolecciones", RecoleccionViewSet, basename="recoleccion")

urlpatterns = [
    path("", include(router.urls)),
]
