"""Pruebas unitarias para el módulo de Familias."""

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from rassa.models import Familia, FamiliaUsuario, Persona, Rol, Usuario


class FamiliasTestCase(TestCase):
    """Caso de prueba para la gestión de Familias."""

    def setUp(self):
        self.client = APIClient()

        # Crear roles necesarios
        self.rol_admin = Rol.objects.create(id_rol=1, nombre_rol="Admin", descripcion="Administrador")
        self.rol_cliente = Rol.objects.create(id_rol=2, nombre_rol="Cliente", descripcion="Cliente")

        # Crear personas y usuarios de prueba
        self.user_admin = User.objects.create_superuser(
            username="admin", email="admin@rassa.com", password="password123"
        )
        self.persona_admin = Persona.objects.create(
            nombre="Admin",
            apellido_paterno="Rassa",
            fecha_nacimiento="1990-01-01",
            sexo="M",
            domicilio="Calle Admin 123",
        )
        self.usuario_admin = Usuario.objects.create(
            fk_user=self.user_admin,
            fk_persona=self.persona_admin,
            telefono="1234567890",
            correo="admin@rassa.com",
            fk_rol=self.rol_admin,
        )

        self.user_cliente1 = User.objects.create_user(
            username="cliente1", email="cliente1@rassa.com", password="password123"
        )
        self.persona_cliente1 = Persona.objects.create(
            nombre="Cliente",
            apellido_paterno="Uno",
            fecha_nacimiento="1995-05-05",
            sexo="F",
            domicilio="Calle Cliente 456",
        )
        self.usuario_cliente1 = Usuario.objects.create(
            fk_user=self.user_cliente1,
            fk_persona=self.persona_cliente1,
            telefono="0987654321",
            correo="cliente1@rassa.com",
            fk_rol=self.rol_cliente,
        )

        self.user_cliente2 = User.objects.create_user(
            username="cliente2", email="cliente2@rassa.com", password="password123"
        )
        self.persona_cliente2 = Persona.objects.create(
            nombre="Cliente",
            apellido_paterno="Dos",
            fecha_nacimiento="1996-06-06",
            sexo="M",
            domicilio="Calle Cliente 789",
        )
        self.usuario_cliente2 = Usuario.objects.create(
            fk_user=self.user_cliente2,
            fk_persona=self.persona_cliente2,
            telefono="1122334455",
            correo="cliente2@rassa.com",
            fk_rol=self.rol_cliente,
        )

        # Autenticar como Admin por defecto
        self.client.force_authenticate(user=self.user_admin)

    def test_crear_familia_exito(self):
        """Valida la creación exitosa de una familia por el administrador."""
        response = self.client.post(
            "/api/familias/grupos/",
            {"nombre_familia": "Familia Test", "detalle_familia": "Detalles de prueba"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["nombre_familia"], "Familia Test")
        self.assertEqual(Familia.objects.filter(nombre_familia="Familia Test").count(), 1)

    def test_crear_familia_nombre_invalido(self):
        """Valida que falle si el nombre es demasiado corto."""
        response = self.client.post(
            "/api/familias/grupos/",
            {"nombre_familia": "Fa", "detalle_familia": "Detalles"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre_familia", response.data)

    def test_exclusividad_miembro_familia(self):
        """Valida que un usuario no pueda pertenecer a más de una familia activa."""
        familia1 = Familia.objects.create(nombre_familia="Familia Uno")
        familia2 = Familia.objects.create(nombre_familia="Familia Dos")

        # Agregar a familia 1 (Exito)
        response1 = self.client.post(
            "/api/familias/miembros/",
            {"fk_usuario": self.usuario_cliente1.id_usuario, "fk_familia": familia1.id_familia},
            format="json",
        )
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

        # Intentar agregar a familia 2 (Fallo de validación)
        response2 = self.client.post(
            "/api/familias/miembros/",
            {"fk_usuario": self.usuario_cliente1.id_usuario, "fk_familia": familia2.id_familia},
            format="json",
        )
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_usuario", response2.data)

    def test_asignar_jefe_familia(self):
        """Valida la asignación y cambio de jefe de familia."""
        familia = Familia.objects.create(nombre_familia="Familia Test")
        # Primero debe ser miembro
        FamiliaUsuario.objects.create(fk_usuario=self.usuario_cliente1, fk_familia=familia)

        # Asignar jefe
        response = self.client.post(
            f"/api/familias/grupos/{familia.id_familia}/asignar-jefe/",
            {"fk_jefe_familia": self.usuario_cliente1.id_usuario},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        familia.refresh_from_db()
        self.assertEqual(familia.fk_jefe_familia, self.usuario_cliente1)

    def test_asignar_jefe_no_miembro(self):
        """Valida que un no miembro no pueda ser asignado como jefe."""
        familia = Familia.objects.create(nombre_familia="Familia Test")
        response = self.client.post(
            f"/api/familias/grupos/{familia.id_familia}/asignar-jefe/",
            {"fk_jefe_familia": self.usuario_cliente1.id_usuario},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_soft_delete_familia_miembros(self):
        """Valida que al eliminar una familia se desactiven lógicamente sus miembros."""
        familia = Familia.objects.create(nombre_familia="Familia Test")
        miembro = FamiliaUsuario.objects.create(fk_usuario=self.usuario_cliente1, fk_familia=familia)

        response = self.client.delete(f"/api/familias/grupos/{familia.id_familia}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        familia.refresh_from_db()
        miembro.refresh_from_db()
        self.assertFalse(familia.estado)
        self.assertFalse(miembro.estado)
