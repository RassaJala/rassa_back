"""Configuración de rutas para el módulo de Recolecciones."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AgricultorListView, RecoleccionViewSet

router = DefaultRouter()
router.register(r"api/recolecciones", RecoleccionViewSet, basename="recoleccion")

urlpatterns = [
    # OJO: esta ruta DEBE ir antes de include(router.urls). El router genera
    # api/recolecciones/<pk>/ con pk=[^/.]+; si esta línea quedara después,
    # "agricultores" matchearía como detalle (pk="agricultores") y devolvería
    # 404. No reordenar sin verificar.
    path("api/recolecciones/agricultores/", AgricultorListView.as_view(), name="recoleccion-agricultores"),
    path("", include(router.urls)),
]
