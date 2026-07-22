"""Vistas para imágenes de productos del catálogo.

Endpoints para gestionar imágenes asociadas a productos:
listar, crear (subir a Google Drive o URL directa), eliminar
y marcar como principal.

Cada producto puede tener múltiples imágenes, pero solo una
puede ser marcada como principal en cualquier momento.
"""

import logging

from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.throttling import ScopedRateThrottle

from rassa.models import Producto, ProductoImagen, PublicacionSemanal
from rassa.permissions.role_permissions import ADMIN, HasRole
from rassa.services.google_drive import delete_file, upload_image
from rassa.views import _ok

from .serializers import ProductoImagenSerializer

logger = logging.getLogger(__name__)

WRITE_METHODS = frozenset({"POST", "PATCH", "DELETE"})

# Permisos por método HTTP. Admin y Agricultor pueden escribir;
# cualquier usuario autenticado puede leer (GET).
PERMISSION_MAP = {
    "GET": [permissions.IsAuthenticated],
    "POST": [permissions.IsAuthenticated, HasRole("Admin", "Agricultor")],
    "PATCH": [permissions.IsAuthenticated, HasRole("Admin", "Agricultor")],
    "DELETE": [permissions.IsAuthenticated, HasRole("Admin", "Agricultor")],
}


class ProductoImagenPagination(PageNumberPagination):
    """Paginación para el listado de imágenes de productos.

    Por defecto muestra 20 imágenes por página.
    El cliente puede solicitar hasta 100 con page_size.
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ProductoImagenViewSet(viewsets.ViewSet):
    """Endpoints para imágenes de productos del catálogo.

    Endpoints disponibles:
    - GET    /api/productos/{id}/imagenes/                  → Listar imágenes
    - POST   /api/productos/{id}/imagenes/                  → Subir imagen (archivo o URL)
    - DELETE /api/productos/{id}/imagenes/{id}/              → Eliminar imagen
    - PATCH  /api/productos/{id}/imagenes/{id}/set-principal/ → Marcar como principal

    El POST acepta:
    - multipart/form-data con campo 'archivo' (imagen que se sube a Google Drive)
    - JSON con campo 'url' (enlace externo directo)
    Al menos una de las dos es requerida.

    La validación de una sola principal por imagen se realiza
    en el endpoint set_principal, no en create.
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "producto_imagen"
    pagination_class = ProductoImagenPagination

    def get_throttles(self):
        """Retorna throttle scope diferente para uploads vs otras operaciones.

        Uploads (POST) usan 'imagen_upload' (20/hour) para limitar
        el uso de Google Drive API. Las demás operaciones usan
        'producto_imagen' (60/hour).
        """
        if self.action == "create":
            throttle = ScopedRateThrottle()
            throttle.scope = "imagen_upload"
            return [throttle]
        return super().get_throttles()

    def get_permissions(self):
        """Retorna permisos según el método HTTP usando PERMISSION_MAP."""
        method = self.request.method
        permission_classes = PERMISSION_MAP.get(method, [permissions.IsAuthenticated])
        return [cls() for cls in permission_classes]

    def _get_producto_or_404(self, producto_id):
        """Busca un producto por ID o lanza NotFound.

        Args:
            producto_id (int): ID del producto a buscar.

        Returns:
            Producto: Instancia del producto encontrado.

        Raises:
            NotFound: Si el producto no existe.
        """
        try:
            return Producto.objects.get(pk=producto_id)
        except Producto.DoesNotExist:
            raise NotFound("Producto no encontrado.") from None

    def _check_ownership(self, request, producto_id):
        """Verifica que un Agricultor tenga permiso sobre las imágenes de un producto.

        Admin siempre tiene acceso. Agricultor solo puede modificar imágenes
        de productos que haya publicado al menos una vez (via PublicacionSemanal).

        Args:
            request: Request HTTP con usuario autenticado.
            producto_id (int): ID del producto.

        Raises:
            PermissionDenied: Si el Agricultor no tiene publicaciones con este producto.
        """
        from rest_framework.exceptions import PermissionDenied

        try:
            rol = request.user.usuario.fk_rol.nombre_rol
        except AttributeError:
            raise PermissionDenied("No se pudo verificar el rol del usuario.") from None

        if rol == ADMIN:
            return

        tiene_publicacion = PublicacionSemanal.objects.filter(
            fk_agricultor=request.user.usuario,
            productosemanal__fk_producto_id=producto_id,
        ).exists()

        if not tiene_publicacion:
            raise PermissionDenied(
                "No tenés publicaciones con este producto. "
                "Solo podés gestionar imágenes de productos que hayas publicado."
            )

    def list(self, request, producto_id=None):
        """Lista todas las imágenes de un producto específico.

        Las imágenes se ordenan por campo 'orden' y luego por ID.
        Respeta la paginación configurada (20 por página, máx 100).

        Args:
            request: Request HTTP con autenticación.
            producto_id (int): ID del producto padre.

        Returns:
            Response: Lista paginada de imágenes del producto.
        """
        self._get_producto_or_404(producto_id)
        imágenes = ProductoImagen.objects.filter(fk_producto_id=producto_id).order_by("orden", "id_imagen")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(imágenes, request)
        if page is not None:
            serializer = ProductoImagenSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        serializer = ProductoImagenSerializer(imágenes, many=True)
        return _ok(data=serializer.data)

    def create(self, request, producto_id=None):
        """Registra una imagen para un producto.

        Acepta dos formas de crear una imagen:
        1. Subir archivo: multipart/form-data con campo 'archivo'
           (se sube a Google Drive y se almacena la URL resultante)
        2. URL directa: JSON con campo 'url' (se almacena tal cual)

        Si la subida a Drive es exitosa pero el guardado en DB falla,
        el archivo remoto se elimina automáticamente (rollback defensivo).

        Args:
            request: Request HTTP con autenticación.
            producto_id (int): ID del producto al que pertenece la imagen.

        Returns:
            Response: Datos de la imagen creada con status 201,
                o error con status 400/502.
        """
        self._get_producto_or_404(producto_id)
        self._check_ownership(request, producto_id)

        archivo = request.FILES.get("archivo")
        url = request.data.get("url", "").strip() if not archivo else None

        if not archivo and not url:
            return _ok(
                message="Debes proporcionar un archivo o una URL.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        drive_file_id = ""
        uploaded_file_id = None
        if archivo:
            try:
                result = upload_image(archivo, archivo.name)
                url = result["url"]
                drive_file_id = result.get("file_id", "")
                uploaded_file_id = drive_file_id
            except ValueError as e:
                return _ok(
                    message=str(e),
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as e:
                logger.error("Error al subir imagen a Google Drive: %s", e)
                return _ok(
                    message="Error al subir la imagen a Google Drive. Intentá de nuevo.",
                    status_code=status.HTTP_502_BAD_GATEWAY,
                )

        data = {
            "fk_producto": producto_id,
            "url": url,
            "es_principal": request.data.get("es_principal", False),
            "orden": request.data.get("orden", 0),
        }

        try:
            with transaction.atomic():
                serializer = ProductoImagenSerializer(data=data)
                serializer.is_valid(raise_exception=True)
                serializer.save(drive_file_id=drive_file_id)
        except ValidationError:
            raise
        except Exception as e:
            if uploaded_file_id:
                try:
                    delete_file(uploaded_file_id)
                except Exception:
                    logger.warning("No se pudo limpiar archivo huérfano %s", uploaded_file_id)
            logger.error("Error al guardar imagen en base de datos: %s", e)
            return _ok(
                message="Error al guardar la imagen. Intentá de nuevo.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return _ok(
            data=serializer.data,
            message="Imagen registrada correctamente.",
            status_code=status.HTTP_201_CREATED,
        )

    def _get_imagen_or_404(self, producto_id, pk):
        """Busca una imagen por ID dentro de un producto o lanza NotFound.

        Args:
            producto_id (int): ID del producto padre.
            pk (int): ID de la imagen a buscar.

        Returns:
            ProductoImagen: Instancia de la imagen encontrada.

        Raises:
            NotFound: Si la imagen no existe para ese producto.
        """
        try:
            return ProductoImagen.objects.get(pk=pk, fk_producto_id=producto_id)
        except ProductoImagen.DoesNotExist:
            raise NotFound("Imagen no encontrada.") from None

    def destroy(self, request, producto_id=None, pk=None):
        """Elimina una imagen de un producto y su archivo en Google Drive.

        Si la imagen tiene un drive_file_id, primero elimina el archivo
        de Google Drive antes de eliminar el registro de la base de datos.
        Si la eliminación de Drive falla, se registra un warning pero
        el registro se elimina igualmente.

        Verifica ownership: Admin puede eliminar cualquier imagen;
        Agricultor solo puede eliminar imágenes de productos publicados.

        Args:
            request: Request HTTP con autenticación.
            producto_id (int): ID del producto padre.
            pk (int): ID de la imagen a eliminar.

        Returns:
            Response: Mensaje de confirmación con status 200.

        Raises:
            NotFound: Si el producto o la imagen no existen.
            PermissionDenied: Si el Agricultor no tiene publicaciones con este producto.
        """
        self._get_producto_or_404(producto_id)
        self._check_ownership(request, producto_id)
        imagen = self._get_imagen_or_404(producto_id, pk)

        if imagen.drive_file_id:
            try:
                delete_file(imagen.drive_file_id)
            except Exception as exc:
                logger.warning("No se pudo eliminar archivo de Drive %s: %s", imagen.drive_file_id, exc)

        imagen.delete()
        return _ok(message="Imagen eliminada correctamente.")

    def partial_update(self, request, producto_id=None, pk=None):
        """Actualiza parcialmente los campos editables de una imagen (URL, orden).

        Verifica ownership: Admin puede actualizar cualquier imagen;
        Agricultor solo puede actualizar imágenes de productos publicados.

        Args:
            request: Request HTTP con autenticación.
            producto_id (int): ID del producto padre.
            pk (int): ID de la imagen a actualizar.

        Returns:
            Response: Datos de la imagen actualizada con status 200.

        Raises:
            NotFound: Si el producto o la imagen no existen.
            PermissionDenied: Si el Agricultor no tiene publicaciones con este producto.
        """
        self._get_producto_or_404(producto_id)
        self._check_ownership(request, producto_id)
        imagen = self._get_imagen_or_404(producto_id, pk)

        allowed_fields = {"url", "orden"}
        data = {k: v for k, v in request.data.items() if k in allowed_fields}

        if not data:
            return _ok(
                message="No se proporcionaron campos para actualizar.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ProductoImagenSerializer(imagen, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return _ok(data=serializer.data, message="Imagen actualizada correctamente.")

    @action(detail=True, methods=["patch"], url_path="set-principal")
    def set_principal(self, request, producto_id=None, pk=None):
        """Marca una imagen como principal del producto.

        Garantiza que solo una imagen sea principal por producto
        usando una transacción atómica: primero desmarca todas las
        imágenes principales del producto, luego marca la seleccionada.

        Verifica ownership: Admin puede marcar cualquier imagen;
        Agricultor solo puede marcar imágenes de productos publicados.

        Args:
            request: Request HTTP con autenticación.
            producto_id (int): ID del producto padre.
            pk (int): ID de la imagen a marcar como principal.

        Returns:
            Response: Datos de la imagen actualizada con status 200.

        Raises:
            NotFound: Si el producto o la imagen no existen.
            PermissionDenied: Si el Agricultor no tiene publicaciones con este producto.
        """
        self._get_producto_or_404(producto_id)
        self._check_ownership(request, producto_id)
        imagen = self._get_imagen_or_404(producto_id, pk)

        with transaction.atomic():
            ProductoImagen.objects.filter(fk_producto_id=producto_id, es_principal=True).update(es_principal=False)
            imagen.es_principal = True
            imagen.save(update_fields=["es_principal"])

        return _ok(
            data=ProductoImagenSerializer(imagen).data,
            message="Imagen marcada como principal.",
        )
