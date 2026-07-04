"""Permisos basados en roles para Django REST Framework.

Implementa el modelo RBAC (Role-Based Access Control) definido en el
documento técnico de RASSA JALA. Cada permiso verifica el rol del
usuario autenticado antes de permitir la ejecución de una acción.

Uso en ViewSets:
    from rassa.permissions.role_permissions import IsAdmin, IsAgricultor

    class ProductoViewSet(viewsets.ModelViewSet):
        def get_permissions(self):
            if self.action == 'destroy':
                return [IsAdmin()]
            return [IsAuthenticated()]

Nota:
    El control de acceso se aplica en la capa de aplicación para
    complementar la validación a nivel de base de datos (función
    usuario_tiene_rol). Ver Sección 9.1 del documento técnico.
"""

from rest_framework import permissions


class IsAdmin(permissions.BasePermission):
    """Permiso para usuarios con rol Administrador.

    Otorga acceso completo a todas las operaciones del sistema.
    Equivale al rol 'Administrador' en la tabla roles.

    Ejemplo de uso:
        permission_classes = [IsAdmin]
    """

    def has_permission(self, request, view):
        """Verifica que el usuario tenga rol Administrador.

        Args:
            request: Objeto Request de DRF.
            view: Vista actual.

        Returns:
            True si el usuario es administrador, False en caso contrario.
        """
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            return request.user.usuario.fk_rol.nombre_rol == "Administrador"
        except AttributeError:
            return False


class IsAgricultor(permissions.BasePermission):
    """Permiso para usuarios con rol Agricultor.

    Permite publicar productos, gestionar stock y registrar mermas.
    Equivale al rol 'Agricultor' en la tabla roles.

    Ejemplo de uso:
        permission_classes = [IsAgricultor]
    """

    def has_permission(self, request, view):
        """Verifica que el usuario tenga rol Agricultor.

        Args:
            request: Objeto Request de DRF.
            view: Vista actual.

        Returns:
            True si el usuario es agricultor, False en caso contrario.
        """
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            return request.user.usuario.fk_rol.nombre_rol == "Agricultor"
        except AttributeError:
            return False


class IsVendedor(permissions.BasePermission):
    """Permiso para usuarios con rol Vendedor.

    Permite gestionar pedidos, registrar entregas y cobros.
    Equivale al rol 'Vendedor' en la tabla roles.

    Ejemplo de uso:
        permission_classes = [IsVendedor]
    """

    def has_permission(self, request, view):
        """Verifica que el usuario tenga rol Vendedor.

        Args:
            request: Objeto Request de DRF.
            view: Vista actual.

        Returns:
            True si el usuario es vendedor, False en caso contrario.
        """
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            return request.user.usuario.fk_rol.nombre_rol == "Vendedor"
        except AttributeError:
            return False


class IsCliente(permissions.BasePermission):
    """Permiso para usuarios con rol Cliente.

    Permite consultar catálogo semanal y seguimiento de pedidos propios.
    Equivale al rol 'Cliente' en la tabla roles.

    Ejemplo de uso:
        permission_classes = [IsCliente]
    """

    def has_permission(self, request, view):
        """Verifica que el usuario tenga rol Cliente.

        Args:
            request: Objeto Request de DRF.
            view: Vista actual.

        Returns:
            True si el usuario es cliente, False en caso contrario.
        """
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            return request.user.usuario.fk_rol.nombre_rol == "Cliente"
        except AttributeError:
            return False


class IsAdminOrAgricultor(permissions.BasePermission):
    """Permiso combinado para Administrador o Agricultor.

    Permite ambas operaciones: gestión completa (Admin) y
    publicación de productos (Agricultor).

    Ejemplo de uso:
        permission_classes = [IsAdminOrAgricultor]
    """

    def has_permission(self, request, view):
        """Verifica que el usuario sea Administrador o Agricultor.

        Args:
            request: Objeto Request de DRF.
            view: Vista actual.

        Returns:
            True si el usuario tiene uno de los dos roles, False en caso contrario.
        """
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            rol = request.user.usuario.fk_rol.nombre_rol
            return rol in ("Administrador", "Agricultor")
        except AttributeError:
            return False


class IsAdminOrVendedor(permissions.BasePermission):
    """Permiso combinado para Administrador o Vendedor.

    Permite operaciones de gestión (Admin) y ventas (Vendedor).

    Ejemplo de uso:
        permission_classes = [IsAdminOrVendedor]
    """

    def has_permission(self, request, view):
        """Verifica que el usuario sea Administrador o Vendedor.

        Args:
            request: Objeto Request de DRF.
            view: Vista actual.

        Returns:
            True si el usuario tiene uno de los dos roles, False en caso contrario.
        """
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            rol = request.user.usuario.fk_rol.nombre_rol
            return rol in ("Administrador", "Vendedor")
        except AttributeError:
            return False


class IsOwnerOrAdmin(permissions.BasePermission):
    """Permiso para propietario del recurso o Administrador.

    Permite acceso al recurso solo si el usuario es el propietario
    o tiene rol Administrador. Útil para gestión de perfil propio.

    Ejemplo de uso:
        permission_classes = [IsOwnerOrAdmin]

    Nota:
        Requiere que el objeto tenga un campo 'usuario' o 'fk_usuario'
        que referencie al usuario propietario.
    """

    def has_object_permission(self, request, view, obj):
        """Verifica propiedad del objeto o rol Administrador.

        Args:
            request: Objeto Request de DRF.
            view: Vista actual.
            obj: Objeto a verificar.

        Returns:
            True si el usuario es propietario o administrador, False en caso contrario.
        """
        if not request.user or not request.user.is_authenticated:
            return False

        # Verificar si es administrador
        try:
            if request.user.usuario.fk_rol.nombre_rol == "Administrador":
                return True
        except AttributeError:
            return False

        # Verificar propiedad del objeto
        if hasattr(obj, "usuario"):
            return obj.usuario == request.user.usuario
        if hasattr(obj, "fk_usuario"):
            return obj.fk_usuario == request.user.usuario
        if hasattr(obj, "fk_cliente"):
            return obj.fk_cliente == request.user.usuario

        return False
