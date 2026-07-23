"""Shared ownership verification for product images.

Consolidates the duplicate _check_ownership logic from
productos_views.py and blueprints/producto_imagen/views.py.
"""

from rest_framework.exceptions import PermissionDenied

from rassa.permissions.role_permissions import ADMIN


def check_producto_ownership(request, producto_id):
    """Verify that an Agricultor has permission over a product's images.

    Admin always passes. Agricultors can only manage images for products
    they have published at least once (via PublicacionSemanal).

    Args:
        request: Authenticated DRF request.
        producto_id (int): Product ID.

    Raises:
        PermissionDenied: If the Agricultor has no publications with this product.
    """
    from rassa.models import PublicacionSemanal

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
