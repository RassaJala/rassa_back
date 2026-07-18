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

from rassa.admin_views import _ensure_single_admin_protected
from rassa.models import Localidad, Log, Municipio, Persona, Rol, Usuario

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
        from rassa.admin_views import AdminUsuarioViewSet

        self._original_throttle = AdminUsuarioViewSet.throttle_classes
        AdminUsuarioViewSet.throttle_classes = []
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

    def tearDown(self):
        from rassa.admin_views import AdminUsuarioViewSet

        AdminUsuarioViewSet.throttle_classes = self._original_throttle

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

    def _create_bulk_users(self, count, prefix="bulk"):
        """Create multiple users for pagination tests."""
        users = []
        for i in range(count):
            u = User.objects.create_user(
                username=f"{prefix}{i}@test.com",
                email=f"{prefix}{i}@test.com",
                password="test1234",
            )
            p = Persona.objects.create(
                nombre=f"User{i}",
                apellido_paterno="Bulk",
                fecha_nacimiento="1990-01-01",
                sexo="M",
                domicilio=f"Calle {i}",
                fk_localidad=self.localidad,
            )
            usuario = Usuario.objects.create(
                fk_user=u,
                fk_persona=p,
                telefono=f"555{i:06d}",
                correo=f"{prefix}{i}@test.com",
                fk_rol=self.rol_buyer,
            )
            users.append(usuario)
        return users

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
        """Admin cannot change their own estado via toggle-estado."""
        response = self.client.patch(
            reverse("admin-usuarios-toggle-estado", args=[self.admin_usuario.id_usuario]),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("propio estado", response.data["detail"])

        self.admin_usuario.refresh_from_db()
        self.assertTrue(self.admin_usuario.estado)

    def test_admin_cannot_activate_self(self):
        """Inactive admin cannot reactivate themselves via toggle-estado."""
        self.admin_usuario.estado = False
        self.admin_usuario.save(update_fields=["estado"])

        response = self.client.patch(
            reverse("admin-usuarios-toggle-estado", args=[self.admin_usuario.id_usuario]),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("propio estado", response.data["detail"])

        self.admin_usuario.refresh_from_db()
        self.assertFalse(self.admin_usuario.estado)

    def test_admin_cannot_deactivate_last_admin(self):
        """No one can deactivate the last active admin."""
        self.admin2_usuario.estado = False
        self.admin2_usuario.save(update_fields=["estado"])

        token = self._login(email=self.admin2_email, password="admin1234")
        response = self.client.patch(
            reverse("admin-usuarios-toggle-estado", args=[self.admin_usuario.id_usuario]),
            format="json",
            **self._auth_header(token),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nico administrador", response.data["detail"])

        self.admin_usuario.refresh_from_db()
        self.assertTrue(self.admin_usuario.estado)

    def test_admin_can_deactivate_when_multiple_admins_exist(self):
        """Admin CAN deactivate another admin when 2+ admins are active."""
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

        token = self._login(email=self.admin2_email, password="admin1234")
        response = self.client.patch(
            reverse("admin-usuarios-toggle-estado", args=[self.admin_usuario.id_usuario]),
            format="json",
            **self._auth_header(token),
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

    def test_partial_update_invalid_role_returns_400(self):
        """partial_update with invalid role returns validation error."""
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.user_usuario.id_usuario]),
            {"role": "invalid_role"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user_usuario.refresh_from_db()
        self.assertEqual(self.user_usuario.fk_rol.nombre_rol, "Cliente")

    def test_partial_update_invalid_localidad_returns_400(self):
        """partial_update with nonexistent localidad returns validation error."""
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.user_usuario.id_usuario]),
            {"fk_localidad": 99999},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_partial_update_invalid_sexo_returns_400(self):
        """partial_update with invalid sexo value returns validation error."""
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.user_usuario.id_usuario]),
            {"sexo": "X"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_partial_update_empty_body_returns_200(self):
        """partial_update with empty body is a no-op, returns 200."""
        original_tel = self.user_usuario.telefono
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.user_usuario.id_usuario]),
            {},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_usuario.refresh_from_db()
        self.assertEqual(self.user_usuario.telefono, original_tel)

    # ==================================================================
    # PASSWORD LEAK PREVENTION
    # ==================================================================

    def test_password_not_exposed_in_list(self):
        """Password field must never appear in list response."""
        response = self.client.get(
            reverse("admin-usuarios-list"),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for user in response.data["data"]["results"]:
            self.assertNotIn("password", user)
            self.assertNotIn("password", str(user))

    def test_password_not_exposed_in_retrieve(self):
        """Password field must never appear in detail response."""
        response = self.client.get(
            reverse("admin-usuarios-detail", args=[self.user_usuario.id_usuario]),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("password", response.data["data"])
        self.assertNotIn("password", str(response.data["data"]))

    # ==================================================================
    # PAGINATION BOUNDARY
    # ==================================================================

    def test_pagination_boundary(self):
        """Pagination works correctly with more users than page_size."""
        self._create_bulk_users(21)

        response = self.client.get(
            reverse("admin-usuarios-list"),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]

        self.assertEqual(data["count"], 24)
        self.assertEqual(len(data["results"]), 20)
        self.assertIsNotNone(data["next"])
        self.assertIsNone(data["previous"])

        # Fetch page 2
        response = self.client.get(
            reverse("admin-usuarios-list"),
            {"page": 2},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data2 = response.data["data"]
        self.assertEqual(data2["count"], 24)
        self.assertEqual(len(data2["results"]), 4)
        self.assertIsNone(data2["next"])
        self.assertIsNotNone(data2["previous"])

    # ==================================================================
    # SEARCH LENGTH LIMIT
    # ==================================================================

    def test_search_exceeding_max_length_returns_empty(self):
        """Search string longer than 100 chars returns empty results."""
        long_search = "a" * 101
        response = self.client.get(
            reverse("admin-usuarios-list"),
            {"search": long_search},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["count"], 0)
        self.assertEqual(response.data["data"]["results"], [])

    def test_search_at_max_length_works(self):
        """Search string at exactly 100 chars still works."""
        search_100 = "admin" * 20
        response = self.client.get(
            reverse("admin-usuarios-list"),
            {"search": search_100},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ==================================================================
    # SPECIAL CHARACTER SEARCH
    # ==================================================================

    def test_search_with_special_characters(self):
        """Search with special characters does not crash."""
        for query in ["O'Brien", "%", "_", "--", "\u00e9\u00f1\u00fc"]:
            response = self.client.get(
                reverse("admin-usuarios-list"),
                {"search": query},
                format="json",
                **self._auth_header(),
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ==================================================================
    # TOGGLE ESTADO — ADDITIONAL SCENARIOS
    # ==================================================================

    def test_toggle_non_admin_user_no_admin_count_check(self):
        """Toggling a non-admin user never triggers admin count validation."""
        response = self.client.patch(
            reverse("admin-usuarios-toggle-estado", args=[self.user_usuario.id_usuario]),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_usuario.refresh_from_db()
        self.assertFalse(self.user_usuario.estado)

    def test_toggle_already_inactive_user_activates(self):
        """Toggling an already inactive user activates them."""
        self.user_usuario.estado = False
        self.user_usuario.save(update_fields=["estado"])

        response = self.client.patch(
            reverse("admin-usuarios-toggle-estado", args=[self.user_usuario.id_usuario]),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_usuario.refresh_from_db()
        self.assertTrue(self.user_usuario.estado)

    # ==================================================================
    # PARTIAL UPDATE — ADDITIONAL SCENARIOS
    # ==================================================================

    def test_partial_update_apellido_materno_null(self):
        """Setting apellido_materno to empty string stores None."""
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.user_usuario.id_usuario]),
            {"apellido_materno": ""},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_usuario.refresh_from_db()
        self.assertIsNone(self.user_usuario.fk_persona.apellido_materno)

    def test_partial_update_fk_localidad(self):
        """Updating fk_localidad changes the user's locality."""
        new_municipio = Municipio.objects.create(nombre="Queretaro")
        new_localidad = Localidad.objects.create(nombre="Juriquilla", fk_municipio=new_municipio)

        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.user_usuario.id_usuario]),
            {"fk_localidad": new_localidad.id_localidad},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_usuario.refresh_from_db()
        self.assertEqual(self.user_usuario.fk_persona.fk_localidad.id_localidad, new_localidad.id_localidad)

    # ==================================================================
    # AUDIT LOGGING (S6)
    # ==================================================================

    def test_audit_log_created_on_partial_update(self):
        """partial_update creates an audit log entry with correct fields."""
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.user_usuario.id_usuario]),
            {"telefono": "7777777777"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        log_entry = Log.objects.filter(descripcion__startswith="Actualización de usuario").latest("creado_en")
        self.assertIn(f"id={self.user_usuario.id_usuario}", log_entry.descripcion)
        self.assertIn("campos=", log_entry.descripcion)

    def test_audit_log_created_on_toggle_estado(self):
        """toggle_estado creates an audit log entry."""
        response = self.client.patch(
            reverse("admin-usuarios-toggle-estado", args=[self.user_usuario.id_usuario]),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        log_entry = Log.objects.filter(descripcion__startswith="Toggle de usuario").latest("creado_en")
        self.assertIn(f"id={self.user_usuario.id_usuario}", log_entry.descripcion)
        self.assertIn("desactivado", log_entry.descripcion)

    # ==================================================================
    # NULL FK_ROL HANDLING (S7)
    # ==================================================================

    def test_ensure_single_admin_protected_null_fk_rol(self):
        """_ensure_single_admin_protected returns None when fk_rol is None."""
        from unittest.mock import MagicMock

        mock_user = MagicMock()
        mock_user.fk_rol = None
        result = _ensure_single_admin_protected(mock_user)
        self.assertIsNone(result)

    # ==================================================================
    # PROTECTED FIELDS (R3-F1 + R3-F4)
    # ==================================================================

    def test_partial_update_ignores_correo_field(self):
        """correo field is not updatable via admin endpoint."""
        original_correo = self.user_usuario.correo
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.user_usuario.id_usuario]),
            {"correo": "hacked@email.com", "telefono": "8888888888"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_usuario.refresh_from_db()
        self.assertEqual(self.user_usuario.correo, original_correo)

    def test_partial_update_ignores_id_field(self):
        """id_usuario cannot be changed via PATCH."""
        original_id = self.user_usuario.id_usuario
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.user_usuario.id_usuario]),
            {"id_usuario": 99999, "telefono": "8888888888"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user_usuario.refresh_from_db()
        self.assertEqual(self.user_usuario.id_usuario, original_id)

    # ==================================================================
    # PAGINATION EDGE CASES (R3-F2)
    # ==================================================================

    def test_pagination_page_zero(self):
        """page=0 is rejected (DRF PageNumberPagination returns 404 for invalid pages)."""
        self._create_bulk_users(25)
        response = self.client.get(
            reverse("admin-usuarios-list"),
            {"page": 0},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_pagination_page_negative(self):
        """page=-1 is rejected (DRF PageNumberPagination returns 404 for invalid pages)."""
        self._create_bulk_users(25)
        response = self.client.get(
            reverse("admin-usuarios-list"),
            {"page": -1},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_pagination_page_beyond_range(self):
        """page=999 returns 404 (DRF PageNumberPagination raises NotFound for out-of-range pages)."""
        response = self.client.get(
            reverse("admin-usuarios-list"),
            {"page": 999},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_pagination_non_numeric_page(self):
        """page=abc returns 404 (DRF PageNumberPagination raises NotFound for non-integer pages)."""
        response = self.client.get(
            reverse("admin-usuarios-list"),
            {"page": "abc"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================================================================
    # PASSWORD NOT IN MUTATION RESPONSES (R3-F5)
    # ==================================================================

    def test_partial_update_response_no_password(self):
        """partial_update response must not expose password."""
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.user_usuario.id_usuario]),
            {"telefono": "8888888888"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("password", response.data["data"])

    def test_toggle_estado_response_no_password(self):
        """toggle_estado response must not expose password."""
        response = self.client.patch(
            reverse("admin-usuarios-toggle-estado", args=[self.user_usuario.id_usuario]),
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("password", response.data["data"])

    # ==================================================================
    # AUDIT LOG ACTOR VALIDATION (R3-W5)
    # ==================================================================

    def test_audit_log_actor_is_requesting_admin(self):
        """Audit log records the admin who performed the action."""
        response = self.client.patch(
            reverse("admin-usuarios-detail", args=[self.user_usuario.id_usuario]),
            {"telefono": "7777777777"},
            format="json",
            **self._auth_header(),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        log_entry = Log.objects.filter(descripcion__startswith="Actualización de usuario").latest("creado_en")
        self.assertEqual(log_entry.fk_usuario.id_usuario, self.admin_usuario.id_usuario)
