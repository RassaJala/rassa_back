"""Tests para protecciones del usuario Admin.

Verifica que un administrador no pueda:
  - Cambiarse su propio rol (se bloquearia del panel admin)
  - Desactivarse a si mismo
  - Desactivar al ultimo administrador activo del sistema

Uso:
    python manage.py test rassa.tests.test_admin_user_protection
"""

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from rassa.models import Localidad, Municipio, Persona, Rol, Usuario

User = get_user_model()


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {},
        "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
        "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
        "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
        "PAGE_SIZE": 20,
        "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    }
)
class AdminUserProtectionTest(APITestCase):
    """Tests para protecciones de integridad del usuario admin."""

    def setUp(self):
        self.rol_admin, _ = Rol.objects.get_or_create(
            nombre_rol="Admin",
            defaults={"descripcion": "Rol Admin"},
        )
        self.rol_buyer, _ = Rol.objects.get_or_create(
            nombre_rol="Cliente",
            defaults={"descripcion": "Rol Cliente"},
        )
        self.rol_seller, _ = Rol.objects.get_or_create(
            nombre_rol="Vendedor",
            defaults={"descripcion": "Rol Vendedor"},
        )

        self.municipio = Municipio.objects.create(nombre="Celaya")
        self.localidad = Localidad.objects.create(nombre="Centro", fk_municipio=self.municipio)

        # Admin principal
        self.admin_email = "admin@rassa.com"
        self.admin_password = "admin1234"
        self.admin_user = User.objects.create_user(
            username=self.admin_email,
            email=self.admin_email,
            password=self.admin_password,
        )
        self.admin_persona = Persona.objects.create(
            nombre="Admin",
            apellido_paterno="Principal",
            fecha_nacimiento="1990-01-01",
            sexo="M",
            domicilio="Calle Admin 1",
            fk_localidad=self.localidad,
        )
        self.admin_usuario = Usuario.objects.create(
            fk_user=self.admin_user,
            fk_persona=self.admin_persona,
            telefono="1111111111",
            correo=self.admin_email,
            fk_rol=self.rol_admin,
        )

        # Segundo admin (para tests de ultimo admin)
        self.admin2_email = "admin2@rassa.com"
        self.admin2_user = User.objects.create_user(
            username=self.admin2_email,
            email=self.admin2_email,
            password="admin1234",
        )
        self.admin2_persona = Persona.objects.create(
            nombre="Admin",
            apellido_paterno="Dos",
            fecha_nacimiento="1991-01-01",
            sexo="M",
            domicilio="Calle Admin 2",
            fk_localidad=self.localidad,
        )
        self.admin2_usuario = Usuario.objects.create(
            fk_user=self.admin2_user,
            fk_persona=self.admin2_persona,
            telefono="2222222222",
            correo=self.admin2_email,
            fk_rol=self.rol_admin,
        )

        # Usuario normal
        self.user_email = "user@rassa.com"
        self.user_user = User.objects.create_user(
            username=self.user_email,
            email=self.user_email,
            password="user1234",
        )
        self.user_persona = Persona.objects.create(
            nombre="Normal",
            apellido_paterno="User",
            fecha_nacimiento="1995-01-01",
            sexo="F",
            domicilio="Calle User 1",
            fk_localidad=self.localidad,
        )
        self.user_usuario = Usuario.objects.create(
            fk_user=self.user_user,
            fk_persona=self.user_persona,
            telefono="3333333333",
            correo=self.user_email,
            fk_rol=self.rol_buyer,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _login(self, email=None, password=None):
        resp = self.client.post(
            reverse("token_obtain_pair"),
            {
                "email": email or self.admin_email,
                "password": password or self.admin_password,
            },
            format="json",
        )
        return resp.data.get("access", "")

    def _auth_header(self, token=None):
        return {"HTTP_AUTHORIZATION": f"Bearer {token or self._login()}"}

    # ==================================================================
    # SELF ROLE CHANGE PREVENTION
    # ==================================================================

    def test_admin_cannot_change_own_role(self):
        """Admin cannot change their own role via partial_update."""
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.admin_usuario.id_usuario]),
            {"role": "buyer"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("propio rol", response.data["detail"])

        # Verify role unchanged in DB
        self.admin_usuario.refresh_from_db()
        self.assertEqual(self.admin_usuario.fk_rol.nombre_rol, "Admin")

    def test_admin_can_update_own_non_role_fields(self):
        """Admin CAN update their own phone, name, etc. (just not role)."""
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.admin_usuario.id_usuario]),
            {"telefono": "9999999999", "nombre": "AdminActualizado"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.admin_usuario.refresh_from_db()
        self.assertEqual(self.admin_usuario.telefono, "9999999999")
        self.assertEqual(self.admin_usuario.fk_persona.nombre, "AdminActualizado")

    def test_admin_can_change_other_user_role(self):
        """Admin CAN change another user's role."""
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.user_usuario.id_usuario]),
            {"role": "seller"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_usuario.refresh_from_db()
        self.assertEqual(self.user_usuario.fk_rol.nombre_rol, "Vendedor")

    # ==================================================================
    # SELF DEACTIVATION PREVENTION
    # ==================================================================

    def test_admin_cannot_deactivate_self(self):
        """Admin cannot deactivate themselves via toggle-estado."""
        response = self.client.patch(
            reverse("admin-usuarios-toggle-estado", args=[self.admin_usuario.id_usuario]),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("propia cuenta", response.data["detail"])

        # Verify still active
        self.admin_usuario.refresh_from_db()
        self.assertTrue(self.admin_usuario.estado)

    # ==================================================================
    # LAST ADMIN DEACTIVATION PREVENTION
    # ==================================================================

    def test_admin_cannot_deactivate_last_admin(self):
        """No one can deactivate the last active admin."""
        # Deactivate second admin so only one remains
        self.admin2_usuario.estado = False
        self.admin2_usuario.save(update_fields=["estado"])

        # admin2 logs in BEFORE deactivation to get a valid JWT
        token = self._login(email=self.admin2_email, password="admin1234")

        # Now admin2 (inactive usuario, but valid JWT) tries to deactivate admin1
        # who is the only active admin
        response = self.client.patch(
            reverse("admin-usuarios-toggle-estado", args=[self.admin_usuario.id_usuario]),
            format="json",
            **self._auth_header(token),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nico administrador", response.data["detail"])

        # Verify still active
        self.admin_usuario.refresh_from_db()
        self.assertTrue(self.admin_usuario.estado)

    def test_admin_can_deactivate_when_multiple_admins_exist(self):
        """Admin CAN deactivate another admin when 2+ admins are active."""
        # Login as admin2, deactivate admin1 (2 admins active)
        token = self._login(email=self.admin2_email, password="admin1234")
        response = self.client.patch(
            reverse("admin-usuarios-toggle-estado", args=[self.admin_usuario.id_usuario]),
            format="json",
            **self._auth_header(token),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.admin_usuario.refresh_from_db()
        self.assertFalse(self.admin_usuario.estado)

    def test_admin_can_activate_last_admin(self):
        """Activating an admin is always allowed (even if they'd be the only one)."""
        self.admin_usuario.estado = False
        self.admin_usuario.save(update_fields=["estado"])

        response = self.client.patch(
            reverse("admin-usuarios-toggle-estado", args=[self.admin_usuario.id_usuario]),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.admin_usuario.refresh_from_db()
        self.assertTrue(self.admin_usuario.estado)

    # ==================================================================
    # HAPPY PATH — CRUD
    # ==================================================================

    def test_admin_can_list_users(self):
        """Admin can list all users."""
        response = self.client.get(
            reverse("admin-usuarios-list"),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("data", response.data)
        results = response.data["data"]["results"]
        self.assertIsInstance(results, list)
        self.assertGreaterEqual(len(results), 3)

    def test_admin_can_retrieve_user(self):
        """Admin can retrieve a specific user's detail."""
        response = self.client.get(
            reverse("admin-usuarios-detail", args=[self.user_usuario.id_usuario]),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("data", response.data)
        self.assertEqual(response.data["data"]["email"], self.user_email)

    def test_admin_can_partial_update_user(self):
        """Admin can update a user's fields."""
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.user_usuario.id_usuario]),
            {"telefono": "5555555555", "nombre": "Editado"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_usuario.refresh_from_db()
        self.assertEqual(self.user_usuario.telefono, "5555555555")
        self.assertEqual(self.user_usuario.fk_persona.nombre, "Editado")

    def test_admin_can_toggle_estado(self):
        """Admin can activate/deactivate a non-admin user."""
        response = self.client.patch(
            reverse("admin-usuarios-toggle-estado", args=[self.user_usuario.id_usuario]),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_usuario.refresh_from_db()
        self.assertFalse(self.user_usuario.estado)

        # Toggle back
        response = self.client.patch(
            reverse("admin-usuarios-toggle-estado", args=[self.user_usuario.id_usuario]),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_usuario.refresh_from_db()
        self.assertTrue(self.user_usuario.estado)

    # ==================================================================
    # UNAUTHORIZED ACCESS
    # ==================================================================

    def test_anonymous_user_gets_401(self):
        """Unauthenticated request returns 401."""
        response = self.client.get(
            reverse("admin-usuarios-list"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_admin_user_gets_403(self):
        """Authenticated non-admin user gets 403."""
        token = self._login(email=self.user_email, password="user1234")
        auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}

        for endpoint in ["admin-usuarios-list", "admin-usuarios-detail"]:
            response = self.client.get(
                reverse(endpoint, args=[] if endpoint == "admin-usuarios-list" else [self.user_usuario.id_usuario]),
                format="json",
                **auth,
            )
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ==================================================================
    # SEARCH & FILTERS
    # ==================================================================

    def test_search_by_name(self):
        """Search by nombre returns matching users."""
        response = self.client.get(
            reverse("admin-usuarios-list"),
            {"search": "Admin"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["data"]["results"]), 2)

    def test_search_by_email(self):
        """Search by correo returns matching users."""
        response = self.client.get(
            reverse("admin-usuarios-list"),
            {"search": "admin@rassa.com"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["data"]["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["email"], "admin@rassa.com")

    def test_filter_by_role(self):
        """Filter by rol returns only users with that role."""
        response = self.client.get(
            reverse("admin-usuarios-list"),
            {"rol": "Cliente"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["data"]["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["email"], self.user_email)

    def test_filter_by_estado(self):
        """Filter by estado returns only users with that state."""
        response = self.client.get(
            reverse("admin-usuarios-list"),
            {"estado": "true"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for user in response.data["data"]["results"]:
            self.assertTrue(user["estado"])

    # ==================================================================
    # NONEXISTENT USER
    # ==================================================================

    def test_partial_update_nonexistent_user_returns_404(self):
        """partial_update returns 404 for nonexistent user."""
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[99999]),
            {"telefono": "1234567890"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("detail", response.data)

    def test_toggle_estado_nonexistent_user_returns_404(self):
        """toggle_estado returns 404 for nonexistent user."""
        response = self.client.patch(
            reverse("admin-usuarios-toggle-estado", args=[99999]),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("detail", response.data)

    # ==================================================================
    # LAST ADMIN ROLE DEMOTION PREVENTION
    # ==================================================================

    def test_admin_cannot_demote_last_admin_role(self):
        """Admin cannot change the last active admin's role to non-admin."""
        self.admin2_usuario.estado = False
        self.admin2_usuario.save(update_fields=["estado"])

        token = self._login(email=self.admin2_email, password="admin1234")
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.admin_usuario.id_usuario]),
            {"role": "buyer"},
            format="json",
            **self._auth_header(token),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unico administrador", response.data["detail"].lower().replace("\u00fa", "u"))

        self.admin_usuario.refresh_from_db()
        self.assertEqual(self.admin_usuario.fk_rol.nombre_rol, "Admin")

    def test_admin_can_demote_admin_when_multiple_exist(self):
        """Admin CAN demote another admin when 2+ active admins exist."""
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.admin2_usuario.id_usuario]),
            {"role": "buyer"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.admin2_usuario.refresh_from_db()
        self.assertEqual(self.admin2_usuario.fk_rol.nombre_rol, "Cliente")

    # ==================================================================
    # TOGGLE ON INACTIVE ADMIN
    # ==================================================================

    def test_toggle_can_activate_inactive_admin(self):
        """Activating an inactive admin is always allowed."""
        self.admin2_usuario.estado = False
        self.admin2_usuario.save(update_fields=["estado"])

        response = self.client.patch(
            reverse("admin-usuarios-toggle-estado", args=[self.admin2_usuario.id_usuario]),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.admin2_usuario.refresh_from_db()
        self.assertTrue(self.admin2_usuario.estado)

    # ==================================================================
    # EMPTY SEARCH
    # ==================================================================

    def test_search_empty_returns_all(self):
        """Empty search string returns all users."""
        response = self.client.get(
            reverse("admin-usuarios-list"),
            {"search": ""},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["data"]["results"]
        self.assertGreaterEqual(len(results), 3)

    # ==================================================================
    # INVALID DATA
    # ==================================================================

    def test_partial_update_invalid_email_returns_400(self):
        """partial_update with invalid data returns validation error."""
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.user_usuario.id_usuario]),
            {"role": "invalid_role"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
