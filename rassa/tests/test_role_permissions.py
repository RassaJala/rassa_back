"""Tests unitarios para permisos RBAC (Role-Based Access Control).

Verifica que HasRole correctly bloquea o permite acceso según el rol
del usuario autenticado, y que los aliases backward-compatible funcionan.

Uso:
    python manage.py test rassa.tests.test_role_permissions
"""

from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory, TestCase

from rassa.models import Persona, Rol, Usuario
from rassa.permissions.role_permissions import (
    ADMIN,
    HasRole,
    IsAdmin,
    IsAdminOrAgricultor,
    IsAdminOrReadOnly,
    IsAdminOrVendedor,
    IsAgricultor,
    IsCliente,
    IsOwnerOrAdmin,
    IsVendedor,
)


def _make_request(user=None):
    """Crea un request mock con el usuario dado."""
    factory = RequestFactory()
    request = factory.get("/test/")
    if user is None:
        request.user = AnonymousUser()
    else:
        request.user = user
    return request


def _make_user_with_rol(nombre_rol, email="test@rassa.com"):
    """Crea un User + Persona + Usuario con el rol indicado, vinculados via fk_user."""
    user = User.objects.create_user(
        username=email,
        email=email,
        password="test1234",
    )
    persona = Persona.objects.create(
        nombre="Test",
        apellido_paterno="User",
        fecha_nacimiento="2000-01-01",
        sexo="M",
        domicilio="Calle Falsa 123",
    )
    rol, _ = Rol.objects.get_or_create(
        nombre_rol=nombre_rol,
        defaults={"descripcion": f"Rol de prueba: {nombre_rol}"},
    )
    usuario = Usuario.objects.create(
        fk_user=user,
        fk_persona=persona,
        telefono="1234567890",
        correo=email,
        fk_rol=rol,
    )
    return user, usuario


class HasRoleTest(TestCase):
    """Tests para el permiso genérico HasRole."""

    def test_single_role_match(self):
        user, _ = _make_user_with_rol(ADMIN)
        perm = HasRole(ADMIN)
        request = _make_request(user)
        self.assertTrue(perm.has_permission(request, None))

    def test_single_role_no_match(self):
        user, _ = _make_user_with_rol("Agricultor")
        perm = HasRole(ADMIN)
        request = _make_request(user)
        self.assertFalse(perm.has_permission(request, None))

    def test_multi_role_match_first(self):
        user, _ = _make_user_with_rol(ADMIN)
        perm = HasRole(ADMIN, "Agricultor")
        request = _make_request(user)
        self.assertTrue(perm.has_permission(request, None))

    def test_multi_role_match_second(self):
        user, _ = _make_user_with_rol("Agricultor")
        perm = HasRole(ADMIN, "Agricultor")
        request = _make_request(user)
        self.assertTrue(perm.has_permission(request, None))

    def test_multi_role_no_match(self):
        user, _ = _make_user_with_rol("Vendedor")
        perm = HasRole(ADMIN, "Agricultor")
        request = _make_request(user)
        self.assertFalse(perm.has_permission(request, None))

    def test_unauthenticated(self):
        perm = HasRole(ADMIN)
        request = _make_request(None)
        self.assertFalse(perm.has_permission(request, None))


class IsAdminOrReadOnlyTest(TestCase):
    """Tests para el permiso IsAdminOrReadOnly."""

    def test_admin_can_write(self):
        user, _ = _make_user_with_rol("Administrador")
        perm = IsAdminOrReadOnly()
        request = _make_request(user)
        request.method = "POST"
        self.assertTrue(perm.has_permission(request, None))

    def test_non_admin_cannot_write(self):
        user, _ = _make_user_with_rol("Cliente")
        perm = IsAdminOrReadOnly()
        request = _make_request(user)
        request.method = "POST"
        self.assertFalse(perm.has_permission(request, None))

    def test_authenticated_user_can_read(self):
        user, _ = _make_user_with_rol("Cliente")
        perm = IsAdminOrReadOnly()
        request = _make_request(user)
        request.method = "GET"
        self.assertTrue(perm.has_permission(request, None))

    def test_unauthenticated_cannot_read(self):
        perm = IsAdminOrReadOnly()
        request = _make_request(None)
        request.method = "GET"
        self.assertFalse(perm.has_permission(request, None))


class BackwardCompatAliasesTest(TestCase):
    """Verifica que los aliases IsAdmin, IsAgricultor, etc. siguen funcionando."""

    def test_admin_alias(self):
        user, _ = _make_user_with_rol(ADMIN)
        self.assertTrue(IsAdmin.has_permission(_make_request(user), None))

    def test_admin_alias_rejects_other(self):
        user, _ = _make_user_with_rol("Agricultor")
        self.assertFalse(IsAdmin.has_permission(_make_request(user), None))

    def test_agricultor_alias(self):
        user, _ = _make_user_with_rol("Agricultor")
        self.assertTrue(IsAgricultor.has_permission(_make_request(user), None))

    def test_vendedor_alias(self):
        user, _ = _make_user_with_rol("Vendedor")
        self.assertTrue(IsVendedor.has_permission(_make_request(user), None))

    def test_cliente_alias(self):
        user, _ = _make_user_with_rol("Cliente")
        self.assertTrue(IsCliente.has_permission(_make_request(user), None))

    def test_admin_or_agricultor_alias(self):
        user1, _ = _make_user_with_rol(ADMIN, "admin@rassa.com")
        user2, _ = _make_user_with_rol("Agricultor", "agri@rassa.com")
        user3, _ = _make_user_with_rol("Vendedor", "vend@rassa.com")
        self.assertTrue(IsAdminOrAgricultor.has_permission(_make_request(user1), None))
        self.assertTrue(IsAdminOrAgricultor.has_permission(_make_request(user2), None))
        self.assertFalse(IsAdminOrAgricultor.has_permission(_make_request(user3), None))

    def test_admin_or_vendedor_alias(self):
        user1, _ = _make_user_with_rol(ADMIN, "admin2@rassa.com")
        user2, _ = _make_user_with_rol("Vendedor", "vend2@rassa.com")
        user3, _ = _make_user_with_rol("Agricultor", "agri2@rassa.com")
        self.assertTrue(IsAdminOrVendedor.has_permission(_make_request(user1), None))
        self.assertTrue(IsAdminOrVendedor.has_permission(_make_request(user2), None))
        self.assertFalse(IsAdminOrVendedor.has_permission(_make_request(user3), None))


class IsOwnerOrAdminTest(TestCase):
    """Tests para el permiso IsOwnerOrAdmin (has_object_permission)."""

    def test_admin_accesa_cualquier_objeto(self):
        user, usuario = _make_user_with_rol(ADMIN)
        perm = IsOwnerOrAdmin()
        request = _make_request(user)
        obj = type("Obj", (), {"fk_usuario": usuario})()
        self.assertTrue(perm.has_object_permission(request, None, obj))

    def test_propietario_accesa_objeto_propio(self):
        user, usuario = _make_user_with_rol("Vendedor")
        perm = IsOwnerOrAdmin()
        request = _make_request(user)
        obj = type("Obj", (), {"fk_usuario": usuario})()
        self.assertTrue(perm.has_object_permission(request, None, obj))

    def test_no_propietario_rechazado(self):
        user1, usuario1 = _make_user_with_rol("Vendedor", "user1@rassa.com")
        _, usuario2 = _make_user_with_rol("Vendedor", "user2@rassa.com")
        perm = IsOwnerOrAdmin()
        request = _make_request(user1)
        obj = type("Obj", (), {"fk_usuario": usuario2})()
        self.assertFalse(perm.has_object_permission(request, None, obj))

    def test_usuario_no_autenticado(self):
        perm = IsOwnerOrAdmin()
        request = _make_request(None)
        obj = type("Obj", (), {"fk_usuario": None})()
        self.assertFalse(perm.has_object_permission(request, None, obj))

    def test_objeto_con_fk_cliente(self):
        user, usuario = _make_user_with_rol("Cliente")
        perm = IsOwnerOrAdmin()
        request = _make_request(user)
        obj = type("Obj", (), {"fk_cliente": usuario})()
        self.assertTrue(perm.has_object_permission(request, None, obj))

    def test_objeto_sin_atributos_usuario(self):
        user, _ = _make_user_with_rol(ADMIN)
        perm = IsOwnerOrAdmin()
        request = _make_request(user)
        obj = object()
        self.assertTrue(perm.has_object_permission(request, None, obj))
