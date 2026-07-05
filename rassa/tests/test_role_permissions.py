"""Tests unitarios para permisos RBAC (Role-Based Access Control).

Verifica que cada permiso (IsAdmin, IsAgricultor, IsVendedor, IsCliente,
IsAdminOrAgricultor, IsAdminOrVendedor, IsOwnerOrAdmin) correctamente
bloquea o permite acceso según el rol del usuario autenticado.

Uso:
    python manage.py test rassa.tests.test_role_permissions
"""

from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory, TestCase

from rassa.models import Persona, Rol, Usuario
from rassa.permissions.role_permissions import (
    IsAdmin,
    IsAdminOrAgricultor,
    IsAdminOrVendedor,
    IsAgricultor,
    IsCliente,
    IsOwnerOrAdmin,
    IsVendedor,
)


def _make_request(user=None):
    """Crea un request mock con el usuario dado.

    Si user es None, crea un request con AnonymousUser.
    Si user es un User real de Django, is_authenticated es True por defecto.
    """
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


class IsAdminTest(TestCase):
    """Tests para el permiso IsAdmin."""

    def test_admin_accesa(self):
        user, _ = _make_user_with_rol("Administrador")
        perm = IsAdmin()
        request = _make_request(user)
        self.assertTrue(perm.has_permission(request, None))

    def test_agricultor_rechazado(self):
        user, _ = _make_user_with_rol("Agricultor")
        perm = IsAdmin()
        request = _make_request(user)
        self.assertFalse(perm.has_permission(request, None))

    def test_vendedor_rechazado(self):
        user, _ = _make_user_with_rol("Vendedor")
        perm = IsAdmin()
        request = _make_request(user)
        self.assertFalse(perm.has_permission(request, None))

    def test_cliente_rechazado(self):
        user, _ = _make_user_with_rol("Cliente")
        perm = IsAdmin()
        request = _make_request(user)
        self.assertFalse(perm.has_permission(request, None))

    def test_usuario_no_autenticado(self):
        perm = IsAdmin()
        request = _make_request(None)
        self.assertFalse(perm.has_permission(request, None))


class IsAgricultorTest(TestCase):
    """Tests para el permiso IsAgricultor."""

    def test_agricultor_accesa(self):
        user, _ = _make_user_with_rol("Agricultor")
        perm = IsAgricultor()
        request = _make_request(user)
        self.assertTrue(perm.has_permission(request, None))

    def test_admin_rechazado(self):
        user, _ = _make_user_with_rol("Administrador")
        perm = IsAgricultor()
        request = _make_request(user)
        self.assertFalse(perm.has_permission(request, None))

    def test_vendedor_rechazado(self):
        user, _ = _make_user_with_rol("Vendedor")
        perm = IsAgricultor()
        request = _make_request(user)
        self.assertFalse(perm.has_permission(request, None))


class IsVendedorTest(TestCase):
    """Tests para el permiso IsVendedor."""

    def test_vendedor_accesa(self):
        user, _ = _make_user_with_rol("Vendedor")
        perm = IsVendedor()
        request = _make_request(user)
        self.assertTrue(perm.has_permission(request, None))

    def test_admin_rechazado(self):
        user, _ = _make_user_with_rol("Administrador")
        perm = IsVendedor()
        request = _make_request(user)
        self.assertFalse(perm.has_permission(request, None))

    def test_agricultor_rechazado(self):
        user, _ = _make_user_with_rol("Agricultor")
        perm = IsVendedor()
        request = _make_request(user)
        self.assertFalse(perm.has_permission(request, None))


class IsClienteTest(TestCase):
    """Tests para el permiso IsCliente."""

    def test_cliente_accesa(self):
        user, _ = _make_user_with_rol("Cliente")
        perm = IsCliente()
        request = _make_request(user)
        self.assertTrue(perm.has_permission(request, None))

    def test_admin_rechazado(self):
        user, _ = _make_user_with_rol("Administrador")
        perm = IsCliente()
        request = _make_request(user)
        self.assertFalse(perm.has_permission(request, None))


class IsAdminOrAgricultorTest(TestCase):
    """Tests para el permiso combinado IsAdminOrAgricultor."""

    def test_admin_accesa(self):
        user, _ = _make_user_with_rol("Administrador")
        perm = IsAdminOrAgricultor()
        request = _make_request(user)
        self.assertTrue(perm.has_permission(request, None))

    def test_agricultor_accesa(self):
        user, _ = _make_user_with_rol("Agricultor")
        perm = IsAdminOrAgricultor()
        request = _make_request(user)
        self.assertTrue(perm.has_permission(request, None))

    def test_vendedor_rechazado(self):
        user, _ = _make_user_with_rol("Vendedor")
        perm = IsAdminOrAgricultor()
        request = _make_request(user)
        self.assertFalse(perm.has_permission(request, None))

    def test_cliente_rechazado(self):
        user, _ = _make_user_with_rol("Cliente")
        perm = IsAdminOrAgricultor()
        request = _make_request(user)
        self.assertFalse(perm.has_permission(request, None))


class IsAdminOrVendedorTest(TestCase):
    """Tests para el permiso combinado IsAdminOrVendedor."""

    def test_admin_accesa(self):
        user, _ = _make_user_with_rol("Administrador")
        perm = IsAdminOrVendedor()
        request = _make_request(user)
        self.assertTrue(perm.has_permission(request, None))

    def test_vendedor_accesa(self):
        user, _ = _make_user_with_rol("Vendedor")
        perm = IsAdminOrVendedor()
        request = _make_request(user)
        self.assertTrue(perm.has_permission(request, None))

    def test_agricultor_rechazado(self):
        user, _ = _make_user_with_rol("Agricultor")
        perm = IsAdminOrVendedor()
        request = _make_request(user)
        self.assertFalse(perm.has_permission(request, None))

    def test_cliente_rechazado(self):
        user, _ = _make_user_with_rol("Cliente")
        perm = IsAdminOrVendedor()
        request = _make_request(user)
        self.assertFalse(perm.has_permission(request, None))


class IsOwnerOrAdminTest(TestCase):
    """Tests para el permiso IsOwnerOrAdmin (has_object_permission)."""

    def test_admin_accesa_cualquier_objeto(self):
        user, usuario = _make_user_with_rol("Administrador")
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
        user, _ = _make_user_with_rol("Administrador")
        perm = IsOwnerOrAdmin()
        request = _make_request(user)
        obj = object()
        self.assertTrue(perm.has_object_permission(request, None, obj))
