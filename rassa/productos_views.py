"""Views for product CRUD endpoints."""

import base64
import binascii
import logging
import uuid

from django.db import transaction
from rest_framework import generics, parsers, permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from rassa.filters import ProductoFilter
from rassa.models import CategoriaProducto, Producto, ProductoImagen, Unidad
from rassa.permissions.role_permissions import IsAdminOrReadOnly
from rassa.productos_serializers import (
    CategoriaSerializer,
    ProductoDetailSerializer,
    ProductoImagenSerializer,
    ProductoListSerializer,
    ProductoUnidadSerializer,
)
from rassa.services.google_drive import delete_image, upload_image
from rassa.views import _ok

EXTENSIONES_PERMITIDAS = {"jpg", "jpeg", "png", "gif", "webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MIME_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}


class ProductoListView(generics.ListCreateAPIView):
    """GET /api/productos/ — list products with filters.
    POST /api/productos/ — create a new product.

    Filtros soportados (query params):
        ?categoria=<id>       Filtrar por categoría
        ?nombre=<texto>       Búsqueda por nombre (parcial)
        ?es_perecedero=true   Filtrar perecederos
        ?precio_min=<n>       Precio mínimo
        ?precio_max=<n>       Precio máximo
        ?unidad=<id>          Filtrar por unidad
    """

    queryset = (
        Producto.objects.select_related("fk_categoria", "fk_unidad")
        .prefetch_related("productoimagen_set")
        .filter(estado=True)
        .order_by("-creado_en")
    )
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = ProductoFilter
    search_fields = ["nombre_producto", "descripcion"]
    ordering_fields = ["nombre_producto", "precio", "creado_en"]

    def get_throttles(self):
        self.throttle_scope = "catalog_write" if self.request.method in ("POST",) else "catalog_read"
        return [ScopedRateThrottle()]

    def get_serializer_class(self):
        if self.request.method in ("POST",):
            return ProductoDetailSerializer
        return ProductoListSerializer

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return _ok(data=response.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return _ok(
            data=serializer.data,
            message="Producto creado exitosamente.",
            status_code=status.HTTP_201_CREATED,
        )


class ProductoDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /api/productos/<id>/"""

    queryset = (
        Producto.objects.select_related("fk_categoria", "fk_unidad")
        .prefetch_related("productoimagen_set")
        .filter(estado=True)
    )
    serializer_class = ProductoDetailSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_throttles(self):
        is_read = self.request.method in ("GET", "HEAD", "OPTIONS")
        self.throttle_scope = "catalog_read" if is_read else "catalog_write"
        return [ScopedRateThrottle()]

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return _ok(data=serializer.data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return _ok(data=serializer.data, message="Producto actualizado exitosamente.")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.estado = False
        instance.save(update_fields=["estado"])
        return _ok(message="Producto eliminado exitosamente.")


class CategoriaListView(generics.ListAPIView):
    """GET /api/categorias/ — list all active categories."""

    queryset = CategoriaProducto.objects.filter(estado=True).order_by("id_categoria")
    serializer_class = CategoriaSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return _ok(data=response.data)


class UnidadListView(generics.ListAPIView):
    """GET /api/unidades/ — list all active units."""

    queryset = Unidad.objects.filter(estado=True).order_by("id_unidad")
    serializer_class = ProductoUnidadSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return _ok(data=response.data)


def _detect_image_format(data):
    """Detect image format from magic bytes. Returns format string or None."""
    if len(data) < 12:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _validar_imagen_bytes(data):
    """Validate that binary data is a recognized image format."""
    return _detect_image_format(data) is not None


def _guardar_imagen_bytes(data, ext, product_id):
    """Save image to Google Drive. Returns (url, drive_file_id)."""
    uid = uuid.uuid4().hex
    filename = f"{uid}.{ext}"
    mime_type = MIME_TYPES.get(ext, "image/jpeg")
    url, file_id = upload_image(data, filename, product_id, mime_type)
    return url, file_id


class ProductoImagenUploadView(APIView):
    """POST /api/productos/<id>/imagen/ — upload or replace product image.

    Acepta:
        - multipart/form-data con campo 'imagen' (archivo)
        - JSON con campo 'imagen_base64' (base64 string)

    Límites: 5 MB máximo, solo imágenes (jpg, jpeg, png, gif, webp).
    """

    permission_classes = [IsAdminOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, parsers.JSONParser]
    throttle_scope = "catalog_write"

    def post(self, request, pk):
        try:
            producto = Producto.objects.get(pk=pk, estado=True)
        except Producto.DoesNotExist:
            return _ok(
                message="Producto no encontrado.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        imagen_archivo = request.FILES.get("imagen")
        data = request.data if isinstance(request.data, dict) else {}
        imagen_base64 = data.get("imagen_base64")

        es_principal_str = str(data.get("es_principal", "true")).lower()
        es_principal = es_principal_str in ("true", "1", "yes")

        url_guardada = None
        drive_file_id = None

        if imagen_archivo:
            if imagen_archivo.size > MAX_FILE_SIZE:
                return _ok(
                    message="El archivo excede el tamaño máximo de 5 MB.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            nombre_raw = imagen_archivo.name or ""
            if "." not in nombre_raw:
                return _ok(
                    message="El archivo debe tener una extensión válida.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            ext = nombre_raw.rsplit(".", 1)[-1].lower()
            if ext not in EXTENSIONES_PERMITIDAS:
                return _ok(
                    message="Tipo de archivo no permitido. Use: jpg, jpeg, png, gif o webp.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            raw_bytes = b"".join(imagen_archivo.chunks())

            if not _validar_imagen_bytes(raw_bytes):
                return _ok(
                    message="El archivo no es una imagen válida.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            try:
                url_guardada, drive_file_id = _guardar_imagen_bytes(raw_bytes, ext, pk)
            except Exception:
                logging.getLogger(__name__).error("Error subiendo imagen a Drive (file upload): %s", exc_info=True)
                return _ok(
                    message="Error al subir la imagen a Google Drive.",
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        elif imagen_base64:
            try:
                if ";" in imagen_base64:
                    imagen_base64 = imagen_base64.split(",", 1)[1]
                raw_bytes = base64.b64decode(imagen_base64)
            except (binascii.Error, ValueError):
                return _ok(
                    message="Formato base64 inválido.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if len(raw_bytes) > MAX_FILE_SIZE:
                return _ok(
                    message="El contenido excede el tamaño máximo de 5 MB.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if not _validar_imagen_bytes(raw_bytes):
                return _ok(
                    message="El contenido no es una imagen válida.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            ext = _detect_image_format(raw_bytes) or "png"
            try:
                url_guardada, drive_file_id = _guardar_imagen_bytes(raw_bytes, ext, pk)
            except Exception:
                logging.getLogger(__name__).error("Error subiendo imagen a Drive (base64): %s", exc_info=True)
                return _ok(
                    message="Error al subir la imagen a Google Drive.",
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            return _ok(
                message="Se requiere el campo 'imagen' (archivo) o 'imagen_base64'.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                if es_principal:
                    ProductoImagen.objects.filter(fk_producto=producto).update(es_principal=False)

                imagen = ProductoImagen.objects.create(
                    fk_producto=producto,
                    url=url_guardada,
                    drive_file_id=drive_file_id,
                    es_principal=es_principal,
                )

                if es_principal:
                    producto.imagen = url_guardada
                    producto.save(update_fields=["imagen"])
        except Exception as exc:
            if drive_file_id:
                delete_image(drive_file_id)
            logging.getLogger(__name__).error("Error guardando imagen en DB: %s", exc, exc_info=True)
            return _ok(
                message="Error al guardar la imagen en la base de datos.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return _ok(
            data=ProductoImagenSerializer(imagen).data,
            message="Imagen subida exitosamente.",
            status_code=status.HTTP_201_CREATED,
        )


class ProductoImagenDeleteView(APIView):
    """DELETE /api/productos/<id>/imagen/<id_imagen>/ — delete a product image."""

    permission_classes = [IsAdminOrReadOnly]
    throttle_scope = "catalog_write"

    def delete(self, request, pk, id_imagen):
        try:
            producto = Producto.objects.get(pk=pk, estado=True)
            imagen = ProductoImagen.objects.get(pk=id_imagen, fk_producto=producto)
        except (Producto.DoesNotExist, ProductoImagen.DoesNotExist):
            return _ok(
                message="Imagen o producto no encontrado.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        was_principal = imagen.es_principal
        drive_file_id = imagen.drive_file_id

        if drive_file_id and not delete_image(drive_file_id):
            return _ok(
                message="Error al eliminar la imagen de Google Drive.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        with transaction.atomic():
            imagen.delete()

            if was_principal:
                otra_imagen = ProductoImagen.objects.filter(fk_producto=producto).first()
                if otra_imagen:
                    otra_imagen.es_principal = True
                    otra_imagen.save(update_fields=["es_principal"])
                    producto.imagen = otra_imagen.url
                else:
                    producto.imagen = None
                producto.save(update_fields=["imagen"])

        return _ok(message="Imagen eliminada exitosamente.")

    def patch(self, request, pk, id_imagen):
        try:
            producto = Producto.objects.get(pk=pk, estado=True)
            imagen = ProductoImagen.objects.get(pk=id_imagen, fk_producto=producto)
        except (Producto.DoesNotExist, ProductoImagen.DoesNotExist):
            return _ok(
                message="Imagen o producto no encontrado.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        es_principal_raw = request.data.get("es_principal")
        if es_principal_raw is None:
            return _ok(
                message="No se proporcionaron cambios.",
                status_code=status.HTTP_200_OK,
            )

        es_principal = str(es_principal_raw).lower() in ("true", "1", "yes")

        if es_principal and not imagen.es_principal:
            with transaction.atomic():
                ProductoImagen.objects.filter(fk_producto=producto).update(es_principal=False)
                imagen.es_principal = True
                imagen.save(update_fields=["es_principal"])
                producto.imagen = imagen.url
                producto.save(update_fields=["imagen"])

        elif not es_principal and imagen.es_principal:
            with transaction.atomic():
                imagen.es_principal = False
                imagen.save(update_fields=["es_principal"])
                otra = ProductoImagen.objects.filter(fk_producto=producto).exclude(pk=imagen.pk).first()
                if otra:
                    otra.es_principal = True
                    otra.save(update_fields=["es_principal"])
                    producto.imagen = otra.url
                else:
                    producto.imagen = None
                producto.save(update_fields=["imagen"])

        return _ok(message="Imagen actualizada exitosamente.")
