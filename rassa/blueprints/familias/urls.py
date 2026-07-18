"""Configuración de rutas para el módulo de Familias."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import FamiliaMiembroViewSet, FamiliaViewSet

router = DefaultRouter()
router.register(r"api/familias/grupos", FamiliaViewSet, basename="familia")
router.register(r"api/familias/miembros", FamiliaMiembroViewSet, basename="familia-miembro")

urlpatterns = [
    path("", include(router.urls)),
]
