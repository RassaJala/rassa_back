from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from rassa.models import Localidad, Municipio, Persona, Rol, Usuario

User = get_user_model()


class ProfileAndAuthEndpointsTest(APITestCase):
    """Test suite para los nuevos endpoints de autenticación y perfil."""

    def setUp(self):
        # Crear roles necesarios
        self.rol_buyer, _ = Rol.objects.get_or_create(
            nombre_rol="Cliente",
            defaults={"descripcion": "Rol Cliente"},
        )
        self.rol_farmer, _ = Rol.objects.get_or_create(
            nombre_rol="Agricultor",
            defaults={"descripcion": "Rol Agricultor"},
        )

        # Crear localidad de prueba
        self.municipio = Municipio.objects.create(nombre="Celaya")
        self.localidad = Localidad.objects.create(nombre="Centro", fk_municipio=self.municipio)

        # Crear un usuario inicial para probar autenticación
        self.email = "test@rassa.com"
        self.password = "password123"
        self.user = User.objects.create_user(
            username=self.email,
            email=self.email,
            password=self.password,
        )
        self.persona = Persona.objects.create(
            nombre="Juan",
            apellido_paterno="Perez",
            fecha_nacimiento="1990-01-01",
            sexo="M",
            domicilio="Calle Falsa 123",
            fk_localidad=self.localidad,
        )
        self.usuario = Usuario.objects.create(
            fk_user=self.user,
            fk_persona=self.persona,
            telefono="1234567890",
            correo=self.email,
            fk_rol=self.rol_buyer,
        )

    def test_register_buyer_success(self):
        url = reverse("register")
        data = {
            "email": "newbuyer@rassa.com",
            "password": "securepassword",
            "telefono": "0987654321",
            "role": "buyer",
            "nombre": "Maria",
            "apellido_paterno": "Lopez",
            "apellido_materno": "Gomez",
            "fecha_nacimiento": "1995-05-15",
            "sexo": "F",
            "domicilio": "Av. Siempre Viva 742",
            "fk_localidad": self.localidad.id_localidad,
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["user"]["email"], "newbuyer@rassa.com")
        self.assertEqual(response.data["user"]["role"], "buyer")
        self.assertEqual(response.data["user"]["nombre"], "Maria")

        # Verificar en base de datos
        db_usuario = Usuario.objects.get(correo="newbuyer@rassa.com")
        self.assertEqual(db_usuario.telefono, "0987654321")
        self.assertEqual(db_usuario.fk_persona.nombre, "Maria")
        self.assertEqual(db_usuario.fk_user.email, "newbuyer@rassa.com")

    def test_register_duplicate_email(self):
        url = reverse("register")
        data = {
            "email": self.email,  # Ya existe
            "password": "securepassword",
            "telefono": "0987654321",
            "role": "buyer",
            "nombre": "Maria",
            "apellido_paterno": "Lopez",
            "fecha_nacimiento": "1995-05-15",
            "sexo": "F",
            "domicilio": "Av. Siempre Viva 742",
            "fk_localidad": self.localidad.id_localidad,
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_get_profile_authenticated(self):
        # Autenticar al cliente
        self.client.force_authenticate(user=self.user)
        url = reverse("me")

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.email)
        self.assertEqual(response.data["nombre"], "Juan")
        self.assertEqual(response.data["role"], "buyer")

    def test_get_profile_unauthenticated(self):
        url = reverse("me")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_profile_success(self):
        self.client.force_authenticate(user=self.user)
        url = reverse("me")
        data = {
            "telefono": "1112223333",
            "nombre": "Juan Carlos",
            "apellido_materno": "Ramirez",
        }

        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["nombre"], "Juan Carlos")
        self.assertEqual(response.data["apellido_materno"], "Ramirez")
        self.assertEqual(response.data["telefono"], "1112223333")

        # Verificar base de datos
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.telefono, "1112223333")
        self.assertEqual(self.usuario.fk_persona.nombre, "Juan Carlos")
        self.assertEqual(self.usuario.fk_persona.apellido_materno, "Ramirez")

    def test_change_password_success(self):
        self.client.force_authenticate(user=self.user)
        url = reverse("change_password")
        data = {
            "old_password": self.password,
            "new_password": "newsecurepassword123",
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])

        # Verificar que el login funciona con la nueva contraseña
        login_success = self.user.check_password("newsecurepassword123")
        self.assertTrue(login_success)

    def test_change_password_invalid_old(self):
        self.client.force_authenticate(user=self.user)
        url = reverse("change_password")
        data = {
            "old_password": "wrongoldpassword",
            "new_password": "newsecurepassword123",
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("old_password", response.data)
