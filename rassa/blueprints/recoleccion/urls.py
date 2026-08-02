"""Configuración de rutas para el módulo de Recolecciones."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AgricultorListView, RecoleccionViewSet

router = DefaultRouter()
router.register(r"api/recolecciones", RecoleccionViewSet, basename="recoleccion")

urlpatterns = [
    path("api/recolecciones/agricultores/", AgricultorListView.as_view(), name="recoleccion-agricultores"),
    path("", include(router.urls)),
]
