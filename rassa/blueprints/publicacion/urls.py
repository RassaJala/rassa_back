from django.urls import path

from .views import ProductoSemanalViewSet, PublicacionViewSet

publicacion_list = PublicacionViewSet.as_view(
    {
        "get": "list",
        "post": "create",
    }
)
publicacion_detail = PublicacionViewSet.as_view(
    {
        "get": "retrieve",
        "delete": "destroy",
    }
)
publicacion_publish = PublicacionViewSet.as_view(
    {
        "post": "publish",
    }
)
publicacion_close = PublicacionViewSet.as_view(
    {
        "post": "close",
    }
)

producto_list = ProductoSemanalViewSet.as_view(
    {
        "get": "list",
        "post": "create",
    }
)
producto_detail = ProductoSemanalViewSet.as_view(
    {
        "patch": "partial_update",
        "delete": "destroy",
    }
)
producto_restore = ProductoSemanalViewSet.as_view(
    {
        "post": "restore",
    }
)

urlpatterns = [
    path("api/publicaciones/", publicacion_list, name="publicacion-list"),
    path("api/publicaciones/<int:pk>/", publicacion_detail, name="publicacion-detail"),
    path("api/publicaciones/<int:pk>/publish/", publicacion_publish, name="publicacion-publish"),
    path("api/publicaciones/<int:pk>/close/", publicacion_close, name="publicacion-close"),
    path("api/publicaciones/<int:pub_id>/productos/", producto_list, name="producto-semanal-list"),
    path("api/publicaciones/<int:pub_id>/productos/<int:pk>/", producto_detail, name="producto-semanal-detail"),
    path(
        "api/publicaciones/<int:pub_id>/productos/<int:pk>/restore/",
        producto_restore,
        name="producto-semanal-restore",
    ),
]
