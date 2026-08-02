"""Permisos basados en roles para Django REST Framework.

Implementa el modelo RBAC (Role-Based Access Control) definido en el
documento técnico de RASSA JALA. Cada permiso verifica el rol del
usuario autenticado antes de permitir la ejecución de una acción.

Uso en ViewSets:
    from rassa.permissions.role_permissions import HasRole, IsOwnerOrAdmin

    class ProductoViewSet(viewsets.ModelViewSet):
        def get_permissions(self):
            if self.action == 'destroy':
                return [HasRole(ADMIN)]
            if self.action in ('create', 'update'):
                return [HasRole(ADMIN, "Agricultor")]
            return [IsAuthenticated()]

Nota:
    El control de acceso se aplica en la capa de aplicación para
    complementar la validación a nivel de base de datos (función
    usuario_tiene_rol). Ver Sección 9.1 del documento técnico.
"""

from rest_framework import permissions

# Valores de rol en BD — usar estas constantes, no strings hardcodeados
ADMIN = "Admin"
AGRICULTOR = "Agricultor"
VENDEDOR = "Vendedor"
CLIENTE = "Cliente"


class HasRole(permissions.BasePermission):
    """Permiso genérico basado en uno o más roles.

    Verifica que el usuario autenticado tenga uno de los roles indicados.

    Uso:
        permission_classes = [HasRole(ADMIN)]
        permission_classes = [HasRole(ADMIN, "Agricultor")]
    """

    def __init__(self, *role_names):
        self.role_names = role_names

    def __call__(self):
        """Allow usage as permission_classes = [HasRole(ADMIN)].

        DRF's get_permissions() calls each element in permission_classes,
        expecting either a class (instantiates it) or a callable instance.
        HasRole instances are callable and return self.
        """
        return self

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        usuario = getattr(request.user, "usuario", None)
        if usuario is None:
            return False
        # Delegar en tiene_rol() (el mismo método que usan las vistas del módulo)
        # en lugar de leer fk_rol.nombre_rol directo: una sola fuente de verdad.
        return any(usuario.tiene_rol(rol) for rol in self.role_names)


class IsOwnerOrAdmin(permissions.BasePermission):
    """Permiso para propietario del recurso o Administrador.

    Permite acceso al recurso solo si el usuario es el propietario
    o tiene rol Administrador. Útil para gestión de perfil propio.

    Uso:
        permission_classes = [IsOwnerOrAdmin]

    Nota:
        Requiere que el objeto tenga un campo 'usuario' o 'fk_usuario'
        que referencie al usuario propietario.
    """

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        try:
            if request.user.usuario.tiene_rol(ADMIN):
                return True
        except AttributeError:
            return False

        if hasattr(obj, "usuario"):
            return obj.usuario == request.user.usuario
        if hasattr(obj, "fk_usuario"):
            return obj.fk_usuario == request.user.usuario
        if hasattr(obj, "fk_cliente"):
            return obj.fk_cliente == request.user.usuario

        return False


class IsAdminOrReadOnly(permissions.BasePermission):
    """Permiso de lectura para autenticados y escritura solo para Administrador.

    Uso:
        permission_classes = [IsAdminOrReadOnly]
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        try:
            return request.user.usuario.tiene_rol(ADMIN)
        except AttributeError:
            return False


# Backward-compatible aliases — prefer HasRole() directly in new code
IsAdmin = HasRole(ADMIN)
IsAgricultor = HasRole(AGRICULTOR)
IsVendedor = HasRole(VENDEDOR)
IsCliente = HasRole(CLIENTE)
IsAdminOrAgricultor = HasRole(ADMIN, AGRICULTOR)
IsAdminOrVendedor = HasRole(ADMIN, VENDEDOR)
