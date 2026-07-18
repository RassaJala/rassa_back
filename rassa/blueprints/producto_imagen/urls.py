from django.urls import path

from .views import ProductoImagenViewSet

urlpatterns = [
    path(
        "api/productos/<int:producto_id>/imagenes/",
        ProductoImagenViewSet.as_view({"get": "list", "post": "create"}),
        name="producto-imagen-list",
    ),
    path(
        "api/productos/<int:producto_id>/imagenes/<int:pk>/",
        ProductoImagenViewSet.as_view({"delete": "destroy"}),
        name="producto-imagen-detail",
    ),
    path(
        "api/productos/<int:producto_id>/imagenes/<int:pk>/set-principal/",
        ProductoImagenViewSet.as_view({"patch": "set_principal"}),
        name="producto-imagen-set-principal",
    ),
]
