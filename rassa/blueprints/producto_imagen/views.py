from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound

from rassa.models import Producto, ProductoImagen
from rassa.permissions.role_permissions import HasRole
from rassa.views import _ok

from .serializers import ProductoImagenSerializer


class ProductoImagenViewSet(viewsets.ViewSet):
    """Endpoints para imágenes de productos del catálogo.

    - GET    /api/productos/{id}/imagenes/                  → Listar
    - POST   /api/productos/{id}/imagenes/                  → Subir
    - DELETE /api/productos/{id}/imagenes/{id}/              → Eliminar
    - PATCH  /api/productos/{id}/imagenes/{id}/set-principal/ → Marcar principal
    """

    permission_classes = [permissions.IsAuthenticated()]

    def get_permissions(self):
        if self.request.method in ("POST", "DELETE", "PATCH"):
            return [permissions.IsAuthenticated(), HasRole("Admin")]
        return [permissions.IsAuthenticated()]

    def _get_producto(self, producto_id):
        try:
            return Producto.objects.get(pk=producto_id)
        except Producto.DoesNotExist:
            raise NotFound("Producto no encontrado.")

    def list(self, request, producto_id=None):
        """Lista imágenes de un producto específico."""
        self._get_producto(producto_id)
        imágenes = ProductoImagen.objects.filter(
            fk_producto_id=producto_id
        ).order_by("orden", "id_imagen")
        serializer = ProductoImagenSerializer(imágenes, many=True)
        return _ok(data=serializer.data)

    def create(self, request, producto_id=None):
        """Registra una imagen para un producto."""
        self._get_producto(producto_id)
        data = request.data.copy()
        data["fk_producto"] = producto_id
        serializer = ProductoImagenSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return _ok(
            data=serializer.data,
            message="Imagen registrada correctamente.",
            status_code=status.HTTP_201_CREATED,
        )

    def destroy(self, request, producto_id=None, pk=None):
        """Elimina una imagen de un producto."""
        self._get_producto(producto_id)
        try:
            imagen = ProductoImagen.objects.get(pk=pk, fk_producto_id=producto_id)
        except ProductoImagen.DoesNotExist:
            raise NotFound("Imagen no encontrada.")
        imagen.delete()
        return _ok(message="Imagen eliminada correctamente.")

    @action(detail=True, methods=["patch"], url_path="set-principal")
    def set_principal(self, request, producto_id=None, pk=None):
        """Marca una imagen como principal (solo una por producto)."""
        self._get_producto(producto_id)
        try:
            imagen = ProductoImagen.objects.get(pk=pk, fk_producto_id=producto_id)
        except ProductoImagen.DoesNotExist:
            raise NotFound("Imagen no encontrada.")

        with transaction.atomic():
            # Quitar principal de todas las imágenes del mismo producto
            ProductoImagen.objects.filter(
                fk_producto_id=producto_id, es_principal=True
            ).update(es_principal=False)
            # Marcar esta como principal
            imagen.es_principal = True
            imagen.save(update_fields=["es_principal"])

        return _ok(
            data=ProductoImagenSerializer(imagen).data,
            message="Imagen marcada como principal.",
        )
