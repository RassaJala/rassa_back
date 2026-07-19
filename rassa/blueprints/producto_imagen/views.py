import logging

from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound

from rassa.models import Producto, ProductoImagen
from rassa.permissions.role_permissions import HasRole
from rassa.services.google_drive import upload_image
from rassa.views import _ok

from .serializers import ProductoImagenSerializer

logger = logging.getLogger(__name__)


class ProductoImagenViewSet(viewsets.ViewSet):
    """Endpoints para imágenes de productos del catálogo.

    - GET    /api/productos/{id}/imagenes/                  → Listar
    - POST   /api/productos/{id}/imagenes/                  → Subir (archivo a Google Drive)
    - DELETE /api/productos/{id}/imagenes/{id}/              → Eliminar
    - PATCH  /api/productos/{id}/imagenes/{id}/set-principal/ → Marcar principal

    El POST acepta multipart/form-data con campo 'archivo' (imagen)
    que se sube a Google Drive y su URL se almacena en el registro.
    Alternativamente se puede enviar 'url' directamente.
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
            raise NotFound("Producto no encontrado.") from None

    def list(self, request, producto_id=None):
        """Lista imágenes de un producto específico."""
        self._get_producto(producto_id)
        imágenes = ProductoImagen.objects.filter(
            fk_producto_id=producto_id
        ).order_by("orden", "id_imagen")
        serializer = ProductoImagenSerializer(imágenes, many=True)
        return _ok(data=serializer.data)

    def create(self, request, producto_id=None):
        """Registra una imagen para un producto.

        Acepta:
        - archivo (file): imagen que se sube a Google Drive
        - url (str): enlace externo directo
        Al menos una de las dos es requerida.
        """
        self._get_producto(producto_id)

        archivo = request.FILES.get("archivo")
        url = request.data.get("url", "").strip() if not archivo else None

        if not archivo and not url:
            return _ok(
                message="Debes proporcionar un archivo o una URL.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Si se sube archivo, subir a Google Drive
        if archivo:
            try:
                url = upload_image(archivo, archivo.name)
            except ValueError as e:
                return _ok(
                    message=str(e),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        data = {
            "fk_producto": producto_id,
            "url": url,
            "es_principal": request.data.get("es_principal", False),
            "orden": request.data.get("orden", 0),
        }

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
            raise NotFound("Imagen no encontrada.") from None
        imagen.delete()
        return _ok(message="Imagen eliminada correctamente.")

    @action(detail=True, methods=["patch"], url_path="set-principal")
    def set_principal(self, request, producto_id=None, pk=None):
        """Marca una imagen como principal (solo una por producto)."""
        self._get_producto(producto_id)
        try:
            imagen = ProductoImagen.objects.get(pk=pk, fk_producto_id=producto_id)
        except ProductoImagen.DoesNotExist:
            raise NotFound("Imagen no encontrada.") from None

        with transaction.atomic():
            ProductoImagen.objects.filter(
                fk_producto_id=producto_id, es_principal=True
            ).update(es_principal=False)
            imagen.es_principal = True
            imagen.save(update_fields=["es_principal"])

        return _ok(
            data=ProductoImagenSerializer(imagen).data,
            message="Imagen marcada como principal.",
        )
