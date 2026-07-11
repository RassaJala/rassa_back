"""Views for product CRUD endpoints."""

import base64
import uuid

from django.conf import settings
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from rassa.filters import ProductoFilter
from rassa.models import CategoriaProducto, Producto, ProductoImagen, Unidad
from rassa.productos_serializers import (
    CategoriaSerializer,
    ProductoDetailSerializer,
    ProductoImagenSerializer,
    ProductoListSerializer,
    UnidadSerializer,
)


def _ok(data=None, message=None, status_code=status.HTTP_200_OK):
    """Standardized success response matching existing backend pattern."""
    body = {}
    if message:
        body["message"] = message
    if data is not None:
        body["data"] = data
    return Response(body, status=status_code)


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
        .all()
        .order_by("-creado_en")
    )
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = ProductoFilter
    search_fields = ["nombre_producto", "descripcion"]
    ordering_fields = ["nombre_producto", "precio", "creado_en"]

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

    queryset = Producto.objects.select_related("fk_categoria", "fk_unidad").all()
    serializer_class = ProductoDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

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
        instance.delete()
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
    serializer_class = UnidadSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return _ok(data=response.data)


class ProductoImagenUploadView(APIView):
    """POST /api/productos/<id>/imagen/ — upload or replace product image.

    Acepta:
        - multipart/form-data con campo 'imagen' (archivo)
        - JSON con campo 'imagen_base64' (base64 string)
    """

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        try:
            producto = Producto.objects.get(pk=pk)
        except Producto.DoesNotExist:
            return _ok(
                message="Producto no encontrado.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        imagen_archivo = request.FILES.get("imagen")
        imagen_base64 = request.data.get("imagen_base64")

        url_guardada = None

        if imagen_archivo:
            ext = imagen_archivo.name.rsplit(".", 1)[-1] if "." in imagen_archivo.name else "png"
            nombre = f"productos/{uuid.uuid4().hex}.{ext}"
            directorio = settings.MEDIA_ROOT / "productos"
            directorio.mkdir(parents=True, exist_ok=True)
            ruta = directorio / f"{uuid.uuid4().hex}.{ext}"
            with open(ruta, "wb") as f:
                for chunk in imagen_archivo.chunks():
                    f.write(chunk)
            url_guardada = f"/media/{nombre}"
        elif imagen_base64:
            try:
                if ";" in imagen_base64:
                    imagen_base64 = imagen_base64.split(",", 1)[1]
                datos = base64.b64decode(imagen_base64)
                nombre = f"productos/{uuid.uuid4().hex}.png"
                directorio = settings.MEDIA_ROOT / "productos"
                directorio.mkdir(parents=True, exist_ok=True)
                ruta = directorio / f"{uuid.uuid4().hex}.png"
                with open(ruta, "wb") as f:
                    f.write(datos)
                url_guardada = f"/media/{nombre}"
            except Exception:
                return _ok(
                    message="Formato base64 inválido.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        else:
            return _ok(
                message="Se requiere el campo 'imagen' (archivo) o 'imagen_base64'.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        imagen = ProductoImagen.objects.create(
            fk_producto=producto,
            url=url_guardada,
            es_principal=True,
        )

        producto.imagen = url_guardada
        producto.save(update_fields=["imagen"])

        return _ok(
            data=ProductoImagenSerializer(imagen).data,
            message="Imagen subida exitosamente.",
            status_code=status.HTTP_201_CREATED,
        )
