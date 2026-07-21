"""Tests for auth endpoints: register, profile, change password.

Response format (standardized):
  Success: { "data": ..., "message": "..." }
  Error:   { "field": ["error msg"] }
"""

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from rassa.models import Localidad, Log, Municipio, Persona, Rol, Usuario
from rassa.permissions.role_permissions import HasRole

User = get_user_model()


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {
            "user": "1000/hour",
            "catalog_read": "60/minute",
            "catalog_write": "60/hour",
        },
        "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
        "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
        "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
        "PAGE_SIZE": 20,
        "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    }
)
class ProfileAndAuthEndpointsTest(APITestCase):
    """Test suite para los endpoints de autenticación y perfil."""

    def setUp(self):
        # Crear roles
        self.rol_buyer, _ = Rol.objects.get_or_create(
            nombre_rol="Cliente",
            defaults={"descripcion": "Rol Cliente"},
        )
        self.rol_farmer, _ = Rol.objects.get_or_create(
            nombre_rol="Agricultor",
            defaults={"descripcion": "Rol Agricultor"},
        )
        self.rol_seller, _ = Rol.objects.get_or_create(
            nombre_rol="Vendedor",
            defaults={"descripcion": "Rol Vendedor"},
        )
        self.rol_admin, _ = Rol.objects.get_or_create(
            nombre_rol="Admin",
            defaults={"descripcion": "Administrador del sistema"},
        )

        # Crear localidad
        self.municipio = Municipio.objects.create(nombre="Celaya")
        self.localidad = Localidad.objects.create(nombre="Centro", fk_municipio=self.municipio)

        # Crear usuario inicial
        self.email = "test@rassa.com"
        self.password = "password123"
        self.user = User.objects.create_user(username=self.email, email=self.email, password=self.password)
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

        # Admin user for create-farmer tests
        self.admin_email = "admin@test.com"
        self.admin_password = "admin123"
        self.admin_user = User.objects.create_user(
            username=self.admin_email,
            email=self.admin_email,
            password=self.admin_password,
        )
        self.admin_persona = Persona.objects.create(
            nombre="Admin",
            apellido_paterno="User",
            fecha_nacimiento="1990-01-01",
            sexo="M",
            domicilio="Admin St",
            fk_localidad=self.localidad,
        )
        self.admin_usuario = Usuario.objects.create(
            fk_user=self.admin_user,
            fk_persona=self.admin_persona,
            telefono="0000000000",
            correo=self.admin_email,
            fk_rol=self.rol_admin,
        )

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _login(self, email=None, password=None):
        """Login and return access token."""
        resp = self.client.post(
            reverse("token_obtain_pair"),
            {"email": email or self.email, "password": password or self.password},
            format="json",
        )
        return resp.data.get("access", "")

    def _auth_header(self, token=None):
        """Authorization header dict."""
        return {"HTTP_AUTHORIZATION": f"Bearer {token or self._login()}"}

    def _admin_auth(self):
        """Authorization header for admin user."""
        token = self._login(email=self.admin_email, password=self.admin_password)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def _create_farmer_data(self, **overrides):
        """Base payload for admin create-farmer endpoint."""
        data = {
            "email": "newfarmer@rassa.com",
            "password": "securepassword",
            "telefono": "0987654321",
            "nombre": "Pedro",
            "apellido_paterno": "Lopez",
            "fecha_nacimiento": "1995-05-15",
            "sexo": "M",
            "domicilio": "Av. Siempre Viva 742",
            "fk_localidad": self.localidad.id_localidad,
        }
        data.update(overrides)
        return data

    def _register_data(self, **overrides):
        """Base registration payload."""
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
        data.update(overrides)
        return data

    # ==================================================================
    # REGISTER
    # ==================================================================

    def test_register_buyer_success(self):
        """Register a buyer and verify response includes JWT tokens."""
        response = self.client.post(reverse("register"), self._register_data(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["message"], "Registro completado exitosamente.")
        data = response.data["data"]
        self.assertEqual(data["email"], "newbuyer@rassa.com")
        self.assertEqual(data["role"], "buyer")
        self.assertEqual(data["nombre"], "Maria")
        self.assertIn("access", data)
        self.assertIn("refresh", data)

        # Verify DB
        db_user = Usuario.objects.get(correo="newbuyer@rassa.com")
        self.assertEqual(db_user.telefono, "0987654321")
        self.assertEqual(db_user.fk_persona.nombre, "Maria")

    def test_register_farmer_rejected(self):
        """Farmer role is NOT available in public register (admin-only creation)."""
        data = self._register_data(email="farmer@rassa.com", role="farmer")
        response = self.client.post(reverse("register"), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_seller_success(self):
        """Register as seller."""
        data = self._register_data(email="seller@rassa.com", role="seller")
        response = self.client.post(reverse("register"), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["role"], "seller")
        # Verify DB role name
        db_user = Usuario.objects.get(correo="seller@rassa.com")
        self.assertEqual(db_user.fk_rol.nombre_rol, "Vendedor")

    def test_admin_create_farmer_success(self):
        """Admin can create a farmer via /api/auth/create-farmer/."""
        data = self._create_farmer_data()
        response = self.client.post(reverse("create-farmer"), data, format="json", **self._admin_auth())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["message"], "Agricultor creado exitosamente.")
        self.assertEqual(response.data["data"]["role"], "farmer")
        # Verify response schema has expected keys
        self.assertIn("access", response.data["data"])
        self.assertIn("refresh", response.data["data"])
        self.assertIn("id_usuario", response.data["data"])
        self.assertIn("email", response.data["data"])
        # Verify DB
        db_user = Usuario.objects.get(correo="newfarmer@rassa.com")
        self.assertEqual(db_user.fk_rol.nombre_rol, "Agricultor")
        # Verify audit log with full content validation
        log_entry = Log.objects.filter(descripcion__startswith="Creación de agricultor por admin").first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.fk_usuario, self.admin_usuario)
        self.assertIn("newfarmer@rassa.com", log_entry.descripcion)
        self.assertIsNotNone(log_entry.ip)
        self.assertIsNotNone(log_entry.dispositivo)

    def test_admin_create_farmer_non_admin_forbidden(self):
        """Non-admin gets 403 when trying to create a farmer."""
        data = self._create_farmer_data()
        response = self.client.post(reverse("create-farmer"), data, format="json", **self._auth_header())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_create_farmer_unauthenticated(self):
        """Unauthenticated request to create-farmer returns 401."""
        data = self._create_farmer_data()
        response = self.client.post(reverse("create-farmer"), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_create_farmer_duplicate_email(self):
        """Admin creating farmer with existing email returns 400."""
        # First create works
        data = self._create_farmer_data()
        resp1 = self.client.post(reverse("create-farmer"), data, format="json", **self._admin_auth())
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)
        # Second with same email fails
        resp2 = self.client.post(reverse("create-farmer"), data, format="json", **self._admin_auth())
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_create_farmer_missing_nombre(self):
        """Create-farmer without nombre returns 400."""
        data = self._create_farmer_data(nombre="")
        resp = self.client.post(reverse("create-farmer"), data, format="json", **self._admin_auth())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre", resp.data)

    def test_admin_create_farmer_missing_email(self):
        """Create-farmer without email returns 400."""
        data = self._create_farmer_data(email="")
        resp = self.client.post(reverse("create-farmer"), data, format="json", **self._admin_auth())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", resp.data)

    def test_admin_create_farmer_missing_telefono(self):
        """Create-farmer without telefono returns 400."""
        data = self._create_farmer_data(telefono="")
        resp = self.client.post(reverse("create-farmer"), data, format="json", **self._admin_auth())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("telefono", resp.data)

    def test_admin_create_farmer_missing_localidad(self):
        """Create-farmer without fk_localidad returns 400."""
        data = self._create_farmer_data(fk_localidad=None)
        resp = self.client.post(reverse("create-farmer"), data, format="json", **self._admin_auth())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_localidad", resp.data)

    def test_admin_create_farmer_invalid_email(self):
        """Create-farmer with malformed email returns 400."""
        data = self._create_farmer_data(email="not-an-email")
        resp = self.client.post(reverse("create-farmer"), data, format="json", **self._admin_auth())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", resp.data)

    def test_admin_create_farmer_invalid_localidad(self):
        """Create-farmer with nonexistent localidad returns 400."""
        data = self._create_farmer_data(fk_localidad=99999)
        resp = self.client.post(reverse("create-farmer"), data, format="json", **self._admin_auth())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_localidad", resp.data)

    def test_admin_create_farmer_short_password(self):
        """Create-farmer with short password returns 400."""
        data = self._create_farmer_data(password="ab")
        resp = self.client.post(reverse("create-farmer"), data, format="json", **self._admin_auth())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", resp.data)

    def test_register_no_apellido_materno(self):
        """Register without apellido_materno."""
        data = self._register_data(email="noam@rassa.com", apellido_materno=None)
        response = self.client.post(reverse("register"), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["data"]["apellido_materno"])

    def test_register_apellido_materno_empty_string(self):
        """Register with empty apellido_materno → stored as None."""
        data = self._register_data(email="emptyam@rassa.com", apellido_materno="")
        response = self.client.post(reverse("register"), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["data"]["apellido_materno"])

    def test_register_duplicate_email(self):
        """Register with existing email returns 400."""
        data = self._register_data(email=self.email)
        response = self.client.post(reverse("register"), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_register_invalid_role(self):
        """Invalid role returns 400."""
        data = self._register_data(role="admin")
        response = self.client.post(reverse("register"), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_invalid_sexo(self):
        """Invalid sexo returns 400."""
        data = self._register_data(sexo="X")
        response = self.client.post(reverse("register"), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_short_password(self):
        """Password shorter than 6 chars returns 400."""
        data = self._register_data(password="abc")
        response = self.client.post(reverse("register"), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_fields(self):
        """Missing required fields return 400."""
        response = self.client.post(reverse("register"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_invalid_localidad(self):
        """Nonexistent localidad returns 400."""
        data = self._register_data(fk_localidad=99999)
        response = self.client.post(reverse("register"), data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_localidad", response.data)

    # ==================================================================
    # LOGIN
    # ==================================================================

    def test_login_success(self):
        """Login returns access and refresh tokens."""
        response = self.client.post(
            reverse("token_obtain_pair"),
            {"email": self.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_ambiguous_error_wrong_email(self):
        """Wrong email returns ambiguous 'credenciales inválidas'."""
        response = self.client.post(
            reverse("token_obtain_pair"),
            {"email": "noexiste@rassa.com", "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("inválidos", str(response.data))

    def test_login_ambiguous_error_wrong_password(self):
        """Wrong password returns the same ambiguous message."""
        response = self.client.post(
            reverse("token_obtain_pair"),
            {"email": self.email, "password": "wrongpass"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("inválidos", str(response.data))

    # ==================================================================
    # GET /me/ — with REAL JWT
    # ==================================================================

    def test_get_profile_authenticated(self):
        """GET /me/ with valid JWT returns profile."""
        token = self._login()
        response = self.client.get(reverse("me"), **self._auth_header(token))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile = response.data["data"]
        self.assertEqual(profile["email"], self.email)
        self.assertEqual(profile["nombre"], "Juan")
        self.assertEqual(profile["role"], "buyer")

    def test_get_profile_unauthenticated(self):
        """No token returns 401."""
        response = self.client.get(reverse("me"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_profile_invalid_token(self):
        """Invalid JWT returns 401."""
        response = self.client.get(reverse("me"), HTTP_AUTHORIZATION="Bearer invalidtoken")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ==================================================================
    # PATCH /me/ — with REAL JWT
    # ==================================================================

    def test_update_profile_success(self):
        """PATCH /me/ updates fields and returns new data."""
        token = self._login()
        url = reverse("me")
        data = {"telefono": "1112223333", "nombre": "Juan Carlos", "apellido_materno": "Ramirez"}

        response = self.client.patch(url, data, format="json", **self._auth_header(token))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile = response.data["data"]
        self.assertEqual(profile["nombre"], "Juan Carlos")
        self.assertEqual(profile["apellido_materno"], "Ramirez")
        self.assertEqual(profile["telefono"], "1112223333")

        # Verify DB
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.telefono, "1112223333")
        self.assertEqual(self.usuario.fk_persona.nombre, "Juan Carlos")

    def test_update_profile_partial(self):
        """PATCH with one field only updates that field."""
        token = self._login()
        response = self.client.patch(
            reverse("me"), {"nombre": "Solo Nombre"}, format="json", **self._auth_header(token)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["nombre"], "Solo Nombre")
        self.assertEqual(response.data["data"]["telefono"], "1234567890")  # unchanged

    def test_update_profile_empty_patch(self):
        """PATCH with empty body succeeds (no-op)."""
        token = self._login()
        response = self.client.patch(reverse("me"), {}, format="json", **self._auth_header(token))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_profile_invalid_localidad(self):
        """PATCH with nonexistent localidad returns 400."""
        token = self._login()
        response = self.client.patch(
            reverse("me"),
            {"fk_localidad": 99999},
            format="json",
            **self._auth_header(token),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ==================================================================
    # CHANGE PASSWORD — with REAL JWT
    # ==================================================================

    def test_change_password_success(self):
        """Change password with correct old password."""
        token = self._login()
        new_pass = "newsecurepassword123"
        response = self.client.post(
            reverse("change_password"),
            {"old_password": self.password, "new_password": new_pass},
            format="json",
            **self._auth_header(token),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Contraseña cambiada exitosamente.")

        # Verify new password works
        new_token = self._login(password=new_pass)
        self.assertIsNotNone(new_token)

    def test_change_password_invalid_old(self):
        """Wrong old password returns 400."""
        token = self._login()
        response = self.client.post(
            reverse("change_password"),
            {"old_password": "wrongoldpassword", "new_password": "newsecurepassword123"},
            format="json",
            **self._auth_header(token),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("old_password", response.data)

    def test_change_password_short_new(self):
        """New password too short returns 400."""
        token = self._login()
        response = self.client.post(
            reverse("change_password"),
            {"old_password": self.password, "new_password": "ab"},
            format="json",
            **self._auth_header(token),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_unauthenticated(self):
        """No token returns 401."""
        response = self.client.post(
            reverse("change_password"),
            {"old_password": "x", "new_password": "y"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ==================================================================
    # LOG — audit trail
    # ==================================================================

    def test_register_creates_log(self):
        """Register creates a Log entry."""
        self.client.post(reverse("register"), self._register_data(), format="json")
        self.assertTrue(Log.objects.filter(descripcion__contains="Registro").exists())

    def test_update_profile_creates_log(self):
        """Profile update creates a Log entry."""
        token = self._login()
        self.client.patch(reverse("me"), {"nombre": "New"}, format="json", **self._auth_header(token))
        self.assertTrue(Log.objects.filter(descripcion__contains="Actualización").exists())

    def test_change_password_creates_log(self):
        """Change password creates a Log entry."""
        token = self._login()
        self.client.post(
            reverse("change_password"),
            {"old_password": self.password, "new_password": "newsecurepassword123"},
            format="json",
            **self._auth_header(token),
        )
        self.assertTrue(Log.objects.filter(descripcion__contains="Cambio de contraseña").exists())

    # ==================================================================
    # NO-PROFILE EDGE CASE
    # ==================================================================

    def test_get_me_no_profile(self):
        """User without Usuario profile gets 404."""
        User.objects.create_user(username="noprofile@test.com", email="noprofile@test.com", password="123pass")
        token = self._login(email="noprofile@test.com", password="123pass")
        response = self.client.get(reverse("me"), **self._auth_header(token))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_me_no_profile(self):
        """PATCH /me/ without Usuario profile returns 404."""
        User.objects.create_user(username="noprofile2@test.com", email="noprofile2@test.com", password="123pass")
        token = self._login(email="noprofile2@test.com", password="123pass")
        response = self.client.patch(reverse("me"), {"nombre": "X"}, format="json", **self._auth_header(token))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================================================================
    # HEALTH CHECK
    # ==================================================================

    def test_auth_health_check(self):
        """GET /auth/health/ returns 200."""
        response = self.client.get(reverse("auth_health"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "ok")

    # ==================================================================
    # TOKEN BLACKLIST on password change
    # ==================================================================

    def test_change_password_blacklists_refresh_token(self):
        """Providing refresh_token on change password blacklists it."""
        token = self._login()
        refresh_token = self.client.post(
            reverse("token_obtain_pair"),
            {"email": self.email, "password": self.password},
            format="json",
        ).data.get("refresh")

        response = self.client.post(
            reverse("change_password"),
            {
                "old_password": self.password,
                "new_password": "newsecurepassword123",
                "refresh_token": refresh_token,
            },
            format="json",
            **self._auth_header(token),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify the blacklisted token can no longer refresh
        refresh_resp = self.client.post(
            reverse("token_refresh"),
            {"refresh": refresh_token},
            format="json",
        )
        self.assertNotEqual(refresh_resp.status_code, status.HTTP_200_OK)

    def test_change_password_without_refresh_token(self):
        """Change password works without providing refresh_token."""
        token = self._login()
        response = self.client.post(
            reverse("change_password"),
            {"old_password": self.password, "new_password": "anothernewpassword456"},
            format="json",
            **self._auth_header(token),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ==================================================================
    # CATALOGOS: municipios and localidades
    # ==================================================================

    def test_list_municipios_success(self):
        """GET /municipios/ returns list of municipios."""
        Municipio.objects.create(id_municipio=100, nombre="Test Municipio")
        token = self._login()
        response = self.client.get(reverse("municipios"), **self._auth_header(token))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertIsInstance(data, list)
        self.assertTrue(any(m["nombre"] == "Test Municipio" for m in data))

    def test_list_municipios_unauthenticated(self):
        """GET /municipios/ without token returns public data (registration flow)."""
        response = self.client.get(reverse("municipios"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data["data"], list)

    def test_list_localidades_success(self):
        """GET /localidades/?municipio_id=X returns localidades."""
        token = self._login()
        response = self.client.get(
            reverse("localidades"),
            {"municipio_id": self.localidad.fk_municipio_id},
            **self._auth_header(token),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertIsInstance(data, list)
        self.assertTrue(any(loc["nombre"] == "Centro" for loc in data))

    def test_list_localidades_missing_param(self):
        """GET /localidades/ without municipio_id returns 400."""
        token = self._login()
        response = self.client.get(reverse("localidades"), **self._auth_header(token))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("municipio_id", response.data)
        self.assertIn("requerido", response.data["municipio_id"])

    def test_list_localidades_invalid_param(self):
        """GET /localidades/?municipio_id=abc returns 400."""
        token = self._login()
        response = self.client.get(reverse("localidades"), {"municipio_id": "abc"}, **self._auth_header(token))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("municipio_id", response.data)
        self.assertIn("entero", response.data["municipio_id"])

    def test_list_localidades_unauthenticated(self):
        """GET /localidades/ without token returns public data (registration flow)."""
        response = self.client.get(reverse("localidades"), {"municipio_id": self.localidad.fk_municipio_id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data["data"], list)

    def test_list_localidades_nonexistent_municipio(self):
        """GET /localidades/?municipio_id=99999 returns empty list."""
        token = self._login()
        response = self.client.get(reverse("localidades"), {"municipio_id": 99999}, **self._auth_header(token))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"], [])

    # ==================================================================
    # PERMISSION TESTS
    # ==================================================================

    def test_has_role_callable_works_as_class(self):
        """HasRole('Admin')() returns self — works in permission_classes."""
        hr = HasRole("Admin")
        self.assertIs(hr(), hr, "HasRole.__call__ must return self for DRF")

    def test_has_role_has_permission_admin(self):
        """HasRole('Admin').has_permission returns True for admin user."""
        hr = HasRole("Admin")
        request = type("Req", (), {"user": self.admin_user, "method": "POST"})()
        self.assertTrue(hr.has_permission(request, None))

    def test_has_role_has_permission_non_admin(self):
        """HasRole('Admin').has_permission returns False for buyer user."""
        hr = HasRole("Admin")
        request = type("Req", (), {"user": self.user, "method": "POST"})()
        self.assertFalse(hr.has_permission(request, None))

    def test_has_role_has_permission_unauthenticated(self):
        """HasRole('Admin').has_permission returns False for anonymous."""
        hr = HasRole("Admin")
        anon = type("User", (), {"is_authenticated": False})()
        request = type("Req", (), {"user": anon, "method": "POST"})()
        self.assertFalse(hr.has_permission(request, None))

    def test_has_role_multi_role(self):
        """HasRole('Admin', 'Agricultor') works with either role."""
        hr = HasRole("Admin", "Agricultor")
        # Admin user passes
        request = type("Req", (), {"user": self.admin_user, "method": "POST"})()
        self.assertTrue(hr.has_permission(request, None))

    # ==================================================================
    # SEARCH USERS TESTS
    # ==================================================================

    def test_search_users_success(self):
        """GET /api/auth/search-users/ with query returns matching active non-admin users."""
        token = self._login(email=self.admin_email, password=self.admin_password)
        # Search for "Juan" (self.usuario has name "Juan")
        response = self.client.get(
            reverse("search-users"),
            {"q": "Juan"},
            **self._auth_header(token)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(response.data["data"][0]["email"], self.email)

    def test_search_users_missing_query_param(self):
        """GET /api/auth/search-users/ without 'q' parameter returns 400 Bad Request."""
        token = self._login(email=self.admin_email, password=self.admin_password)
        response = self.client.get(
            reverse("search-users"),
            {},
            **self._auth_header(token)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("q", response.data)

    def test_search_users_query_too_short(self):
        """GET /api/auth/search-users/ with query < 3 chars returns 400 Bad Request."""
        token = self._login(email=self.admin_email, password=self.admin_password)
        response = self.client.get(
            reverse("search-users"),
            {"q": "Ju"},
            **self._auth_header(token)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("q", response.data)

    def test_search_users_excludes_admins(self):
        """GET /api/auth/search-users/ does not return Admin users."""
        token = self._login(email=self.admin_email, password=self.admin_password)
        # Search for "Admin" (self.admin_usuario has name "Admin")
        response = self.client.get(
            reverse("search-users"),
            {"q": "Admin"},
            **self._auth_header(token)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 0)

    def test_search_users_excludes_users_with_family(self):
        """GET /api/auth/search-users/ does not return users already in an active family."""
        # Create a family and add self.usuario to it
        from rassa.models import Familia, FamiliaUsuario
        familia = Familia.objects.create(nombre_familia="Familia Test")
        FamiliaUsuario.objects.create(fk_usuario=self.usuario, fk_familia=familia)

        token = self._login(email=self.admin_email, password=self.admin_password)
        # Search for "Juan" (should now be excluded because they are in an active family)
        response = self.client.get(
            reverse("search-users"),
            {"q": "Juan"},
            **self._auth_header(token)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]), 0)

