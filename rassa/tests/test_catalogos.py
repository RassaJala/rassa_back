"""Tests for catalogos CRUD: municipios and localidades.

Response format (standardized):
  Success: { "data": ..., "message": "..." }
  Error:   { "field": ["error msg"] }
"""

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from rassa.models import Localidad, Municipio, Persona, Rol, Usuario

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
class CatalogosCRUDTest(APITestCase):
    """Test suite para CRUD de municipios y localidades."""

    def setUp(self):
        """Create Admin + Agricultor users, one municipio + one localidad fixture."""
        # -- Roles --
        self.rol_admin, _ = Rol.objects.get_or_create(
            nombre_rol="Admin",
            defaults={"descripcion": "Administrador del sistema"},
        )
        self.rol_agricultor, _ = Rol.objects.get_or_create(
            nombre_rol="Agricultor",
            defaults={"descripcion": "Rol Agricultor"},
        )

        # -- Fixture data --
        self.municipio = Municipio.objects.create(nombre="Celaya")
        self.municipio2 = Municipio.objects.create(nombre="Irapuato")
        self.localidad = Localidad.objects.create(nombre="Centro", fk_municipio=self.municipio)

        # -- Admin user --
        self.admin_user = User.objects.create_user(
            username="admin@test.com",
            email="admin@test.com",
            password="admin123",
        )
        admin_persona = Persona.objects.create(
            nombre="Admin",
            apellido_paterno="User",
            fecha_nacimiento="1990-01-01",
            sexo="M",
            domicilio="Admin St",
            fk_localidad=self.localidad,
        )
        self.admin_usuario = Usuario.objects.create(
            fk_user=self.admin_user,
            fk_persona=admin_persona,
            telefono="0000000000",
            correo="admin@test.com",
            fk_rol=self.rol_admin,
        )

        # -- Non-admin (Agricultor) user --
        self.nonadmin_user = User.objects.create_user(
            username="agri@test.com",
            email="agri@test.com",
            password="agri123",
        )
        nonadmin_persona = Persona.objects.create(
            nombre="Non",
            apellido_paterno="Admin",
            fecha_nacimiento="1990-01-01",
            sexo="M",
            domicilio="Nonadmin St",
            fk_localidad=self.localidad,
        )
        self.nonadmin_usuario = Usuario.objects.create(
            fk_user=self.nonadmin_user,
            fk_persona=nonadmin_persona,
            telefono="1111111111",
            correo="agri@test.com",
            fk_rol=self.rol_agricultor,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_token(self, email):
        """Generate JWT locally without hitting the token endpoint (avoids rate limits)."""
        user = User.objects.get(email=email)
        return str(AccessToken.for_user(user))

    def _admin_auth(self):
        """Authorization header for admin."""
        return {"HTTP_AUTHORIZATION": f"Bearer {self._make_token('admin@test.com')}"}

    def _nonadmin_auth(self):
        """Authorization header for non-admin."""
        return {"HTTP_AUTHORIZATION": f"Bearer {self._make_token('agri@test.com')}"}

    # ==================================================================
    # Municipio CRUD
    # ==================================================================

    # --- LIST ---

    def test_municipio_list_admin_success(self):
        """Admin can list municipios."""
        Municipio.objects.create(nombre="Test MX")
        resp = self.client.get(reverse("municipios"), **self._admin_auth())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertIsInstance(data, list)
        names = [m["nombre"] for m in data]
        self.assertIn("Celaya", names)
        self.assertIn("Test MX", names)

    def test_municipio_list_nonadmin_success(self):
        """Non-admin can also list municipios (safe method)."""
        resp = self.client.get(reverse("municipios"), **self._nonadmin_auth())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsInstance(resp.data["data"], list)

    def test_municipio_list_unauthenticated(self):
        """GET /municipios/ without token returns public data (registration flow)."""
        resp = self.client.get(reverse("municipios"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsInstance(resp.data["data"], list)

    # --- CREATE ---

    def test_municipio_create_admin_success(self):
        """Admin can create a municipio."""
        resp = self.client.post(
            reverse("municipios"),
            {"nombre": "Nuevo Municipio"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("message", resp.data)
        self.assertEqual(resp.data["data"]["nombre"], "Nuevo Municipio")
        self.assertTrue(Municipio.objects.filter(nombre="Nuevo Municipio").exists())

    def test_municipio_create_unauthenticated(self):
        """Unauthenticated POST to /municipios/ returns 401."""
        resp = self.client.post(
            reverse("municipios"),
            {"nombre": "Should Fail"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_municipio_create_nonadmin_forbidden(self):
        """Non-admin gets 403 when creating a municipio."""
        resp = self.client.post(
            reverse("municipios"),
            {"nombre": "No deberia"},
            format="json",
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_municipio_create_empty_name(self):
        """Creating municipio with empty/whitespace name returns 400."""
        for empty_val in ["", "   "]:
            resp = self.client.post(
                reverse("municipios"),
                {"nombre": empty_val},
                format="json",
                **self._admin_auth(),
            )
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("nombre", resp.data)

    def test_municipio_create_name_too_long(self):
        """Creating municipio with name over 100 chars returns 400."""
        resp = self.client.post(
            reverse("municipios"),
            {"nombre": "A" * 101},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre", resp.data)

    # --- DETAIL ---

    def test_municipio_detail_admin_success(self):
        """Admin can GET a municipio detail."""
        resp = self.client.get(
            reverse("municipio-detail", kwargs={"pk": self.municipio.id_municipio}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["nombre"], "Celaya")

    def test_municipio_detail_nonadmin_success(self):
        """Non-admin can GET municipio detail (safe method)."""
        resp = self.client.get(
            reverse("municipio-detail", kwargs={"pk": self.municipio.id_municipio}),
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["nombre"], "Celaya")

    # --- UPDATE ---

    def test_municipio_update_admin_success(self):
        """Admin can PUT (update) a municipio."""
        resp = self.client.put(
            reverse("municipio-detail", kwargs={"pk": self.municipio.id_municipio}),
            {"nombre": "Celaya Actualizado"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.municipio.refresh_from_db()
        self.assertEqual(self.municipio.nombre, "Celaya Actualizado")

    def test_municipio_update_nonadmin_forbidden(self):
        """Non-admin gets 403 when updating a municipio."""
        resp = self.client.put(
            reverse("municipio-detail", kwargs={"pk": self.municipio.id_municipio}),
            {"nombre": "Hacked"},
            format="json",
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # --- DELETE ---

    def test_municipio_delete_admin_success(self):
        """Admin can soft-delete a municipio (estado=False)."""
        temp = Municipio.objects.create(nombre="Temp")
        resp = self.client.delete(
            reverse("municipio-detail", kwargs={"pk": temp.id_municipio}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        # Soft-delete: record still exists, but estado=False
        temp.refresh_from_db()
        self.assertFalse(temp.estado)

    def test_municipio_delete_nonadmin_forbidden(self):
        """Non-admin gets 403 when deleting a municipio."""
        resp = self.client.delete(
            reverse("municipio-detail", kwargs={"pk": self.municipio.id_municipio}),
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # ==================================================================
    # Localidad CRUD
    # ==================================================================

    # --- CREATE via nested route ---

    def test_localidad_create_via_nested_admin_success(self):
        """Admin can create a localidad via nested route."""
        url = reverse("localidades-by-municipio", kwargs={"pk": self.municipio.id_municipio})
        resp = self.client.post(
            url,
            {"nombre": "Nueva Colonia"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn("message", resp.data)
        self.assertEqual(resp.data["data"]["nombre"], "Nueva Colonia")
        self.assertTrue(Localidad.objects.filter(nombre="Nueva Colonia", fk_municipio=self.municipio).exists())

    def test_localidad_create_via_nested_unauthenticated(self):
        """Unauthenticated POST to /municipios/{pk}/localidades/ returns 401."""
        url = reverse("localidades-by-municipio", kwargs={"pk": self.municipio.id_municipio})
        resp = self.client.post(
            url,
            {"nombre": "Should Fail"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_localidad_create_via_nested_nonadmin_forbidden(self):
        """Non-admin gets 403 when creating a localidad."""
        url = reverse("localidades-by-municipio", kwargs={"pk": self.municipio.id_municipio})
        resp = self.client.post(
            url,
            {"nombre": "No deberia"},
            format="json",
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # --- LIST via nested route ---

    def test_localidad_list_via_nested_admin_success(self):
        """Admin can list localidades by municipio via nested route."""
        Localidad.objects.create(nombre="Barrio Nuevo", fk_municipio=self.municipio)
        url = reverse("localidades-by-municipio", kwargs={"pk": self.municipio.id_municipio})
        resp = self.client.get(url, **self._admin_auth())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        names = [loc["nombre"] for loc in data]
        self.assertIn("Centro", names)
        self.assertIn("Barrio Nuevo", names)

    def test_localidad_list_via_nested_nonadmin_success(self):
        """Non-admin can also list localidades (safe method)."""
        url = reverse("localidades-by-municipio", kwargs={"pk": self.municipio.id_municipio})
        resp = self.client.get(url, **self._nonadmin_auth())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # --- DETAIL ---

    def test_localidad_detail_admin_success(self):
        """Admin can GET a localidad detail."""
        resp = self.client.get(
            reverse("localidad-detail", kwargs={"pk": self.localidad.id_localidad}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["nombre"], "Centro")

    def test_localidad_detail_nonadmin_success(self):
        """Non-admin can GET localidad detail (safe method)."""
        resp = self.client.get(
            reverse("localidad-detail", kwargs={"pk": self.localidad.id_localidad}),
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["nombre"], "Centro")

    # --- UPDATE ---

    def test_localidad_update_admin_success(self):
        """Admin can PUT (update) a localidad."""
        resp = self.client.put(
            reverse("localidad-detail", kwargs={"pk": self.localidad.id_localidad}),
            {"nombre": "Centro Actualizado"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.localidad.refresh_from_db()
        self.assertEqual(self.localidad.nombre, "Centro Actualizado")

    def test_localidad_update_nonadmin_forbidden(self):
        """Non-admin gets 403 when updating a localidad."""
        resp = self.client.put(
            reverse("localidad-detail", kwargs={"pk": self.localidad.id_localidad}),
            {"nombre": "Hacked"},
            format="json",
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # --- DELETE ---

    def test_localidad_delete_admin_success(self):
        """Admin can soft-delete a localidad (estado=False)."""
        temp = Localidad.objects.create(nombre="Temp", fk_municipio=self.municipio)
        resp = self.client.delete(
            reverse("localidad-detail", kwargs={"pk": temp.id_localidad}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        # Soft-delete: record still exists, but estado=False
        temp.refresh_from_db()
        self.assertFalse(temp.estado)

    def test_localidad_delete_nonadmin_forbidden(self):
        """Non-admin gets 403 when deleting a localidad."""
        resp = self.client.delete(
            reverse("localidad-detail", kwargs={"pk": self.localidad.id_localidad}),
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # ==================================================================
    # Nested route scoping (4.4)
    # ==================================================================

    def test_nested_route_scoping(self):
        """Localidades returned match the URL municipio."""
        # Create one localidad in municipio 1, two in municipio 2
        Localidad.objects.create(nombre="Solo En M1", fk_municipio=self.municipio)
        Localidad.objects.create(nombre="En M2 A", fk_municipio=self.municipio2)
        Localidad.objects.create(nombre="En M2 B", fk_municipio=self.municipio2)

        url_m1 = reverse("localidades-by-municipio", kwargs={"pk": self.municipio.id_municipio})
        url_m2 = reverse("localidades-by-municipio", kwargs={"pk": self.municipio2.id_municipio})
        auth = self._admin_auth()

        resp_m1 = self.client.get(url_m1, **auth)
        resp_m2 = self.client.get(url_m2, **auth)

        names_m1 = [loc["nombre"] for loc in resp_m1.data["data"]]
        names_m2 = [loc["nombre"] for loc in resp_m2.data["data"]]

        self.assertIn("Solo En M1", names_m1)
        self.assertNotIn("Solo En M1", names_m2)
        self.assertIn("En M2 A", names_m2)
        self.assertNotIn("En M2 A", names_m1)

        # The fixture localidad "Centro" is in municipio 1
        self.assertIn("Centro", names_m1)
        self.assertNotIn("Centro", names_m2)

    # ==================================================================
    # Backward compat (4.5)
    # ==================================================================

    def test_localidades_backward_compat_success(self):
        """GET /api/localidades/?municipio_id=X still works."""
        resp = self.client.get(
            reverse("localidades"),
            {"municipio_id": self.municipio.id_municipio},
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertIsInstance(data, list)
        self.assertTrue(any(loc["nombre"] == "Centro" for loc in data))

    def test_localidades_backward_compat_empty(self):
        """GET /api/localidades/?municipio_id=99999 returns empty list."""
        resp = self.client.get(
            reverse("localidades"),
            {"municipio_id": 99999},
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"], [])

    def test_localidades_backward_compat_missing_param(self):
        """GET /api/localidades/ without municipio_id returns 400."""
        resp = self.client.get(reverse("localidades"), **self._admin_auth())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # ==================================================================
    # 404 on nonexistent IDs (4.6)
    # ==================================================================

    def test_municipio_detail_not_found(self):
        """GET /municipios/99999/ returns 404."""
        resp = self.client.get(
            reverse("municipio-detail", kwargs={"pk": 99999}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_municipio_update_not_found(self):
        """PUT /municipios/99999/ returns 404."""
        resp = self.client.put(
            reverse("municipio-detail", kwargs={"pk": 99999}),
            {"nombre": "N/A"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_municipio_delete_not_found(self):
        """DELETE /municipios/99999/ returns 404."""
        resp = self.client.delete(
            reverse("municipio-detail", kwargs={"pk": 99999}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_localidad_detail_not_found(self):
        """GET /localidades/99999/ returns 404."""
        resp = self.client.get(
            reverse("localidad-detail", kwargs={"pk": 99999}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_localidad_update_not_found(self):
        """PUT /localidades/99999/ returns 404."""
        resp = self.client.put(
            reverse("localidad-detail", kwargs={"pk": 99999}),
            {"nombre": "N/A"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_localidad_delete_not_found(self):
        """DELETE /localidades/99999/ returns 404."""
        resp = self.client.delete(
            reverse("localidad-detail", kwargs={"pk": 99999}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # ==================================================================
    # Localidad backward compat: municipio_id in body on create
    # ==================================================================

    def test_localidad_create_backward_compat_admin_success(self):
        """Admin can create localidad via backward compat path with municipio_id query param."""
        url = reverse("localidades") + f"?municipio_id={self.municipio.id_municipio}"
        resp = self.client.post(
            url,
            {"nombre": "BackCompat Localidad"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Localidad.objects.filter(nombre="BackCompat Localidad", fk_municipio=self.municipio).exists())

    def test_localidad_create_backward_compat_nonadmin_forbidden(self):
        """Non-admin gets 403 creating localidad via backward compat."""
        url = reverse("localidades") + f"?municipio_id={self.municipio.id_municipio}"
        resp = self.client.post(
            url,
            {"nombre": "No"},
            format="json",
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # ==================================================================
    # PATCH tests (4.7)
    # ==================================================================

    def test_municipio_patch_admin_success(self):
        """Admin can PATCH a municipio (partial update)."""
        resp = self.client.patch(
            reverse("municipio-detail", kwargs={"pk": self.municipio.id_municipio}),
            {"nombre": "Celaya Patch"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.municipio.refresh_from_db()
        self.assertEqual(self.municipio.nombre, "Celaya Patch")

    def test_municipio_patch_nonadmin_forbidden(self):
        """Non-admin gets 403 when PATCHing a municipio."""
        resp = self.client.patch(
            reverse("municipio-detail", kwargs={"pk": self.municipio.id_municipio}),
            {"nombre": "Hacked"},
            format="json",
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_localidad_patch_admin_success(self):
        """Admin can PATCH a localidad (partial update)."""
        resp = self.client.patch(
            reverse("localidad-detail", kwargs={"pk": self.localidad.id_localidad}),
            {"nombre": "Centro Patch"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.localidad.refresh_from_db()
        self.assertEqual(self.localidad.nombre, "Centro Patch")

    def test_localidad_patch_nonadmin_forbidden(self):
        """Non-admin gets 403 when PATCHing a localidad."""
        resp = self.client.patch(
            reverse("localidad-detail", kwargs={"pk": self.localidad.id_localidad}),
            {"nombre": "Hacked"},
            format="json",
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # ==================================================================
    # Localidad create validation (4.8)
    # ==================================================================

    def test_localidad_create_empty_name(self):
        """Creating localidad with empty/whitespace name returns 400."""
        for empty_val in ["", "   "]:
            resp = self.client.post(
                reverse("localidades-by-municipio", kwargs={"pk": self.municipio.id_municipio}),
                {"nombre": empty_val},
                format="json",
                **self._admin_auth(),
            )
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("nombre", resp.data)

    def test_localidad_create_name_too_long(self):
        """Creating localidad with name over model max_length returns 400."""
        resp = self.client.post(
            reverse("localidades-by-municipio", kwargs={"pk": self.municipio.id_municipio}),
            {"nombre": "A" * 151},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre", resp.data)

    def test_localidad_create_via_nested_nonexistent_municipio(self):
        """POST /api/municipios/99999/localidades/ returns 400."""
        resp = self.client.post(
            reverse("localidades-by-municipio", kwargs={"pk": 99999}),
            {"nombre": "Nowhere"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("municipio", resp.data)

    def test_localidad_create_via_nested_soft_deleted_municipio(self):
        """POST /api/municipios/{soft-deleted}/localidades/ returns 400."""
        temp = Municipio.objects.create(nombre="DeletedMuni")
        temp.estado = False
        temp.save(update_fields=["estado"])
        resp = self.client.post(
            reverse("localidades-by-municipio", kwargs={"pk": temp.id_municipio}),
            {"nombre": "Nowhere"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("municipio", resp.data)

    def test_localidad_create_backward_compat_soft_deleted_municipio(self):
        """POST /api/localidades/?municipio_id={soft-deleted} returns 400."""
        temp = Municipio.objects.create(nombre="DeletedMuni")
        temp.estado = False
        temp.save(update_fields=["estado"])
        resp = self.client.post(
            reverse("localidades") + f"?municipio_id={temp.id_municipio}",
            {"nombre": "Nowhere"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("municipio_id", resp.data)

    def test_localidad_create_backward_compat_missing_param(self):
        """POST /api/localidades/ without municipio_id returns 400."""
        resp = self.client.post(
            reverse("localidades"),
            {"nombre": "No Municipio"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("municipio_id", resp.data)

    def test_localidad_create_backward_compat_bad_param(self):
        """POST /api/localidades/?municipio_id=abc returns 400."""
        resp = self.client.post(
            reverse("localidades") + "?municipio_id=abc",
            {"nombre": "Bad Municipio"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("municipio_id", resp.data)

    def test_localidad_create_backward_compat_nonexistent_municipio(self):
        """POST /api/localidades/?municipio_id=99999 returns 400."""
        resp = self.client.post(
            reverse("localidades") + "?municipio_id=99999",
            {"nombre": "Nowhere"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("municipio_id", resp.data)

    # ==================================================================
    # Soft-delete isolation (4.9)
    # ==================================================================

    def test_soft_deleted_municipio_excluded_from_list(self):
        """Soft-deleted municipio should not appear in list."""
        temp = Municipio.objects.create(nombre="TempParaBorrar")
        temp.estado = False
        temp.save(update_fields=["estado"])
        resp = self.client.get(reverse("municipios"), **self._admin_auth())
        names = [m["nombre"] for m in resp.data["data"]]
        self.assertNotIn("TempParaBorrar", names)

    def test_soft_deleted_localidad_excluded_from_list(self):
        """Soft-deleted localidad should not appear in list."""
        temp = Localidad.objects.create(nombre="TempParaBorrar", fk_municipio=self.municipio)
        temp.estado = False
        temp.save(update_fields=["estado"])
        url = reverse("localidades-by-municipio", kwargs={"pk": self.municipio.id_municipio})
        resp = self.client.get(url, **self._admin_auth())
        names = [loc["nombre"] for loc in resp.data["data"]]
        self.assertNotIn("TempParaBorrar", names)

    # ==================================================================
    # UPDATE/PATCH validation (Review PR #39 — WARNING 7)
    # ==================================================================

    def test_municipio_update_empty_name(self):
        """PUT with empty/whitespace name returns 400."""
        for empty_val in ["", "   "]:
            resp = self.client.put(
                reverse("municipio-detail", kwargs={"pk": self.municipio.id_municipio}),
                {"nombre": empty_val},
                format="json",
                **self._admin_auth(),
            )
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("nombre", resp.data)

    def test_municipio_update_name_too_long(self):
        """PUT with name over model max_length returns 400."""
        resp = self.client.put(
            reverse("municipio-detail", kwargs={"pk": self.municipio.id_municipio}),
            {"nombre": "A" * 101},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre", resp.data)

    def test_municipio_patch_empty_name(self):
        """PATCH with empty name returns 400."""
        resp = self.client.patch(
            reverse("municipio-detail", kwargs={"pk": self.municipio.id_municipio}),
            {"nombre": ""},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre", resp.data)

    def test_localidad_update_empty_name(self):
        """PUT localidad with empty/whitespace name returns 400."""
        for empty_val in ["", "   "]:
            resp = self.client.put(
                reverse("localidad-detail", kwargs={"pk": self.localidad.id_localidad}),
                {"nombre": empty_val},
                format="json",
                **self._admin_auth(),
            )
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("nombre", resp.data)

    def test_localidad_update_name_too_long(self):
        """PUT localidad with name over model max_length returns 400."""
        resp = self.client.put(
            reverse("localidad-detail", kwargs={"pk": self.localidad.id_localidad}),
            {"nombre": "A" * 151},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre", resp.data)

    def test_localidad_patch_empty_name(self):
        """PATCH localidad with empty name returns 400."""
        resp = self.client.patch(
            reverse("localidad-detail", kwargs={"pk": self.localidad.id_localidad}),
            {"nombre": ""},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre", resp.data)

    # ==================================================================
    # Soft-deleted records via detail (Review PR #39 — WARNING 7)
    # ==================================================================

    def test_soft_deleted_municipio_detail_returns_404(self):
        """GET soft-deleted municipio detail returns 404."""
        temp = Municipio.objects.create(nombre="Temp")
        temp.estado = False
        temp.save(update_fields=["estado"])
        resp = self.client.get(
            reverse("municipio-detail", kwargs={"pk": temp.id_municipio}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_soft_deleted_municipio_update_returns_404(self):
        """PUT soft-deleted municipio returns 404."""
        temp = Municipio.objects.create(nombre="Temp")
        temp.estado = False
        temp.save(update_fields=["estado"])
        resp = self.client.put(
            reverse("municipio-detail", kwargs={"pk": temp.id_municipio}),
            {"nombre": "Nuevo"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_soft_deleted_municipio_delete_returns_404(self):
        """DELETE soft-deleted municipio returns 404."""
        temp = Municipio.objects.create(nombre="Temp")
        temp.estado = False
        temp.save(update_fields=["estado"])
        resp = self.client.delete(
            reverse("municipio-detail", kwargs={"pk": temp.id_municipio}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # ==================================================================
    # Restore endpoint (Review PR #39 — WARNING 8)
    # ==================================================================

    def test_municipio_restore_admin_success(self):
        """Admin can restore a soft-deleted municipio."""
        temp = Municipio.objects.create(nombre="Temp")
        temp.estado = False
        temp.save(update_fields=["estado"])
        resp = self.client.post(
            reverse("municipio-restore", kwargs={"pk": temp.id_municipio}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("message", resp.data)
        temp.refresh_from_db()
        self.assertTrue(temp.estado)

    def test_municipio_restore_nonadmin_forbidden(self):
        """Non-admin gets 403 when restoring a municipio."""
        temp = Municipio.objects.create(nombre="Temp")
        temp.estado = False
        temp.save(update_fields=["estado"])
        resp = self.client.post(
            reverse("municipio-restore", kwargs={"pk": temp.id_municipio}),
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_localidad_restore_admin_success(self):
        """Admin can restore a soft-deleted localidad."""
        temp = Localidad.objects.create(nombre="Temp", fk_municipio=self.municipio)
        temp.estado = False
        temp.save(update_fields=["estado"])
        resp = self.client.post(
            reverse("localidad-restore", kwargs={"pk": temp.id_localidad}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("message", resp.data)
        temp.refresh_from_db()
        self.assertTrue(temp.estado)

    def test_localidad_restore_nonadmin_forbidden(self):
        """Non-admin gets 403 when restoring a localidad."""
        temp = Localidad.objects.create(nombre="Temp", fk_municipio=self.municipio)
        temp.estado = False
        temp.save(update_fields=["estado"])
        resp = self.client.post(
            reverse("localidad-restore", kwargs={"pk": temp.id_localidad}),
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # ==================================================================
    # Localidad soft-deleted isolation (Review v3 — W1)
    # ==================================================================

    def test_soft_deleted_localidad_detail_returns_404(self):
        """GET soft-deleted localidad detail returns 404."""
        temp = Localidad.objects.create(nombre="Temp", fk_municipio=self.municipio)
        temp.estado = False
        temp.save(update_fields=["estado"])
        resp = self.client.get(
            reverse("localidad-detail", kwargs={"pk": temp.id_localidad}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_soft_deleted_localidad_update_returns_404(self):
        """PUT soft-deleted localidad returns 404."""
        temp = Localidad.objects.create(nombre="Temp", fk_municipio=self.municipio)
        temp.estado = False
        temp.save(update_fields=["estado"])
        resp = self.client.put(
            reverse("localidad-detail", kwargs={"pk": temp.id_localidad}),
            {"nombre": "Nuevo"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_soft_deleted_localidad_delete_returns_404(self):
        """DELETE soft-deleted localidad returns 404."""
        temp = Localidad.objects.create(nombre="Temp", fk_municipio=self.municipio)
        temp.estado = False
        temp.save(update_fields=["estado"])
        resp = self.client.delete(
            reverse("localidad-detail", kwargs={"pk": temp.id_localidad}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # ==================================================================
    # PATCH max length validation (Review v3 — W2)
    # ==================================================================

    def test_municipio_patch_name_too_long(self):
        """PATCH municipio with name over max_length returns 400."""
        resp = self.client.patch(
            reverse("municipio-detail", kwargs={"pk": self.municipio.id_municipio}),
            {"nombre": "A" * 101},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre", resp.data)

    def test_localidad_patch_name_too_long(self):
        """PATCH localidad with name over max_length returns 400."""
        resp = self.client.patch(
            reverse("localidad-detail", kwargs={"pk": self.localidad.id_localidad}),
            {"nombre": "A" * 151},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre", resp.data)

    # ==================================================================
    # Cambiar estado (activar/desactivar)
    # ==================================================================

    def test_municipio_cambiar_estado_admin_desactivar(self):
        """Admin can desactivar (estado=false) a municipio."""
        resp = self.client.patch(
            reverse("municipio-cambiar-estado", kwargs={"pk": self.municipio.id_municipio}),
            {"estado": False},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("message", resp.data)
        self.municipio.refresh_from_db()
        self.assertFalse(self.municipio.estado)

    def test_municipio_cambiar_estado_admin_activar(self):
        """Admin can reactivar (estado=true) a soft-deleted municipio."""
        self.municipio.estado = False
        self.municipio.save(update_fields=["estado"])
        resp = self.client.patch(
            reverse("municipio-cambiar-estado", kwargs={"pk": self.municipio.id_municipio}),
            {"estado": True},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.municipio.refresh_from_db()
        self.assertTrue(self.municipio.estado)

    def test_municipio_cambiar_estado_nonadmin_forbidden(self):
        """Non-admin gets 403 when changing estado."""
        resp = self.client.patch(
            reverse("municipio-cambiar-estado", kwargs={"pk": self.municipio.id_municipio}),
            {"estado": False},
            format="json",
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_municipio_cambiar_estado_unauthenticated(self):
        """Unauthenticated gets 401 when changing estado."""
        resp = self.client.patch(
            reverse("municipio-cambiar-estado", kwargs={"pk": self.municipio.id_municipio}),
            {"estado": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_municipio_cambiar_estado_not_found(self):
        """PATCH /municipios/99999/estado/ returns 404."""
        resp = self.client.patch(
            reverse("municipio-cambiar-estado", kwargs={"pk": 99999}),
            {"estado": False},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_municipio_cambiar_estado_missing_field(self):
        """PATCH without estado field returns 400."""
        resp = self.client.patch(
            reverse("municipio-cambiar-estado", kwargs={"pk": self.municipio.id_municipio}),
            {},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estado", resp.data)

    def test_municipio_cambiar_estado_invalid_type(self):
        """PATCH with non-boolean estado returns 400."""
        resp = self.client.patch(
            reverse("municipio-cambiar-estado", kwargs={"pk": self.municipio.id_municipio}),
            {"estado": "no es bool"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estado", resp.data)

    # --- Localidad cambiar estado ---

    def test_localidad_cambiar_estado_admin_desactivar(self):
        """Admin can desactivar (estado=false) a localidad."""
        resp = self.client.patch(
            reverse("localidad-cambiar-estado", kwargs={"pk": self.localidad.id_localidad}),
            {"estado": False},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("message", resp.data)
        self.localidad.refresh_from_db()
        self.assertFalse(self.localidad.estado)

    def test_localidad_cambiar_estado_admin_activar(self):
        """Admin can reactivar (estado=true) a soft-deleted localidad."""
        self.localidad.estado = False
        self.localidad.save(update_fields=["estado"])
        resp = self.client.patch(
            reverse("localidad-cambiar-estado", kwargs={"pk": self.localidad.id_localidad}),
            {"estado": True},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.localidad.refresh_from_db()
        self.assertTrue(self.localidad.estado)

    def test_localidad_cambiar_estado_nonadmin_forbidden(self):
        """Non-admin gets 403 when changing estado."""
        resp = self.client.patch(
            reverse("localidad-cambiar-estado", kwargs={"pk": self.localidad.id_localidad}),
            {"estado": False},
            format="json",
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_localidad_cambiar_estado_unauthenticated(self):
        """Unauthenticated gets 401 when changing estado."""
        resp = self.client.patch(
            reverse("localidad-cambiar-estado", kwargs={"pk": self.localidad.id_localidad}),
            {"estado": False},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_localidad_cambiar_estado_not_found(self):
        """PATCH /localidades/99999/estado/ returns 404."""
        resp = self.client.patch(
            reverse("localidad-cambiar-estado", kwargs={"pk": 99999}),
            {"estado": False},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_localidad_cambiar_estado_missing_field(self):
        """PATCH without estado field returns 400."""
        resp = self.client.patch(
            reverse("localidad-cambiar-estado", kwargs={"pk": self.localidad.id_localidad}),
            {},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estado", resp.data)

    def test_localidad_cambiar_estado_invalid_type(self):
        """PATCH with non-boolean estado returns 400."""
        resp = self.client.patch(
            reverse("localidad-cambiar-estado", kwargs={"pk": self.localidad.id_localidad}),
            {"estado": "no es bool"},
            format="json",
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estado", resp.data)

    # ==================================================================
    # Trash — listar inactivos
    # ==================================================================

    def test_municipio_trash_list_admin_success(self):
        """Admin can list soft-deleted municipios in trash."""
        Municipio.objects.create(nombre="Eliminado Test")
        temp = Municipio.objects.get(nombre="Eliminado Test")
        temp.estado = False
        temp.save(update_fields=["estado"])

        resp = self.client.get(
            reverse("municipios-trash"),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("data", resp.data)
        names = [m["nombre"] for m in resp.data["data"]]
        self.assertIn("Eliminado Test", names)
        self.assertNotIn("Celaya", names)  # Celaya is active, not in trash

    def test_municipio_trash_list_unauthenticated(self):
        """Unauthenticated can list trash (public read)."""
        resp = self.client.get(reverse("municipios-trash"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("data", resp.data)

    def test_municipio_trash_list_empty(self):
        """Trash returns empty list when no records are inactive."""
        resp = self.client.get(
            reverse("municipios-trash"),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["data"]), 0)

    def test_municipio_trash_list_includes_estado_field(self):
        """Trash response includes estado field (should be False)."""
        temp = Municipio.objects.create(nombre="Inactivo Test")
        temp.estado = False
        temp.save(update_fields=["estado"])

        resp = self.client.get(
            reverse("municipios-trash"),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for item in resp.data["data"]:
            self.assertIn("estado", item)
            self.assertFalse(item["estado"])

    def test_localidad_trash_list_admin_success(self):
        """Admin can list soft-deleted localidades in trash."""
        temp = Localidad.objects.create(
            nombre="Localidad Eliminada",
            fk_municipio=self.municipio,
        )
        temp.estado = False
        temp.save(update_fields=["estado"])

        resp = self.client.get(
            reverse("localidades-trash"),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("data", resp.data)
        names = [loc["nombre"] for loc in resp.data["data"]]
        self.assertIn("Localidad Eliminada", names)
        self.assertNotIn("Centro", names)  # Centro is active

    def test_localidad_trash_list_unauthenticated(self):
        """Unauthenticated can list localidad trash (public read)."""
        resp = self.client.get(reverse("localidades-trash"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("data", resp.data)

    # ==================================================================
    # Permanent delete (hard delete)
    # ==================================================================

    def test_municipio_permanent_delete_admin_success(self):
        """Admin can permanently delete a soft-deleted municipio."""
        temp = Municipio.objects.create(nombre="Para Eliminar")
        temp.estado = False
        temp.save(update_fields=["estado"])

        resp = self.client.post(
            reverse("municipio-permanent", kwargs={"pk": temp.id_municipio}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("message", resp.data)
        # Verify it's actually gone
        self.assertFalse(Municipio.objects.filter(pk=temp.id_municipio).exists())

    def test_municipio_permanent_delete_active_forbidden(self):
        """Cannot permanently delete an active municipio."""
        resp = self.client.post(
            reverse("municipio-permanent", kwargs={"pk": self.municipio.id_municipio}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        # Record should still exist
        self.assertTrue(Municipio.objects.filter(pk=self.municipio.id_municipio).exists())

    def test_municipio_permanent_delete_nonadmin_forbidden(self):
        """Non-admin gets 403 for permanent delete."""
        temp = Municipio.objects.create(nombre="Temporal")
        temp.estado = False
        temp.save(update_fields=["estado"])

        resp = self.client.post(
            reverse("municipio-permanent", kwargs={"pk": temp.id_municipio}),
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_municipio_permanent_delete_unauthenticated(self):
        """Unauthenticated gets 401 for permanent delete."""
        temp = Municipio.objects.create(nombre="Temporal")
        temp.estado = False
        temp.save(update_fields=["estado"])

        resp = self.client.post(
            reverse("municipio-permanent", kwargs={"pk": temp.id_municipio}),
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_municipio_permanent_delete_not_found(self):
        """Permanent delete on non-existent pk returns 404."""
        resp = self.client.post(
            reverse("municipio-permanent", kwargs={"pk": 99999}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_localidad_permanent_delete_admin_success(self):
        """Admin can permanently delete a soft-deleted localidad."""
        temp = Localidad.objects.create(
            nombre="Localidad Temp",
            fk_municipio=self.municipio,
        )
        temp.estado = False
        temp.save(update_fields=["estado"])

        resp = self.client.post(
            reverse("localidad-permanent", kwargs={"pk": temp.id_localidad}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("message", resp.data)
        self.assertFalse(Localidad.objects.filter(pk=temp.id_localidad).exists())

    def test_localidad_permanent_delete_active_forbidden(self):
        """Cannot permanently delete an active localidad."""
        resp = self.client.post(
            reverse("localidad-permanent", kwargs={"pk": self.localidad.id_localidad}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Localidad.objects.filter(pk=self.localidad.id_localidad).exists())

    def test_localidad_permanent_delete_nonadmin_forbidden(self):
        """Non-admin gets 403 for permanent delete of localidad."""
        temp = Localidad.objects.create(
            nombre="Temp Localidad",
            fk_municipio=self.municipio,
        )
        temp.estado = False
        temp.save(update_fields=["estado"])

        resp = self.client.post(
            reverse("localidad-permanent", kwargs={"pk": temp.id_localidad}),
            **self._nonadmin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_localidad_permanent_delete_not_found(self):
        """Permanent delete on non-existent localidad pk returns 404."""
        resp = self.client.post(
            reverse("localidad-permanent", kwargs={"pk": 99999}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # ==================================================================
    # CASCADE protection
    # ==================================================================

    def test_municipio_permanent_delete_cascade_blocked(self):
        """Cannot hard-delete a municipio that has associated localidades."""
        temp_muni = Municipio.objects.create(nombre="Muni con Hijos")
        temp_muni.estado = False
        temp_muni.save(update_fields=["estado"])
        # Create a localidad (even inactive) under this municipio
        Localidad.objects.create(
            nombre="Hija",
            fk_municipio=temp_muni,
            estado=False,
        )

        resp = self.client.post(
            reverse("municipio-permanent", kwargs={"pk": temp_muni.id_municipio}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # Municipio should still exist
        self.assertTrue(Municipio.objects.filter(pk=temp_muni.id_municipio).exists())
        # Localidad should still exist too
        self.assertTrue(Localidad.objects.filter(fk_municipio=temp_muni).exists())

    def test_municipio_permanent_delete_cascade_allowed_no_hijos(self):
        """Can hard-delete a municipio WITHOUT associated localidades."""
        temp_muni = Municipio.objects.create(nombre="Muni Solitario")
        temp_muni.estado = False
        temp_muni.save(update_fields=["estado"])

        resp = self.client.post(
            reverse("municipio-permanent", kwargs={"pk": temp_muni.id_municipio}),
            **self._admin_auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(Municipio.objects.filter(pk=temp_muni.id_municipio).exists())

    def test_municipio_permanent_delete_twice_returns_404(self):
        """Second permanent delete on same pk returns 404."""
        temp = Municipio.objects.create(nombre="Doble Delete")
        temp.estado = False
        temp.save(update_fields=["estado"])

        # First delete succeeds
        resp1 = self.client.post(
            reverse("municipio-permanent", kwargs={"pk": temp.id_municipio}),
            **self._admin_auth(),
        )
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)

        # Second delete returns 404 (already gone)
        resp2 = self.client.post(
            reverse("municipio-permanent", kwargs={"pk": temp.id_municipio}),
            **self._admin_auth(),
        )
        self.assertEqual(resp2.status_code, status.HTTP_404_NOT_FOUND)

    def test_localidad_permanent_delete_twice_returns_404(self):
        """Second permanent delete on same localidad pk returns 404."""
        temp = Localidad.objects.create(
            nombre="Doble Delete Localidad",
            fk_municipio=self.municipio,
        )
        temp.estado = False
        temp.save(update_fields=["estado"])

        resp1 = self.client.post(
            reverse("localidad-permanent", kwargs={"pk": temp.id_localidad}),
            **self._admin_auth(),
        )
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)

        resp2 = self.client.post(
            reverse("localidad-permanent", kwargs={"pk": temp.id_localidad}),
            **self._admin_auth(),
        )
        self.assertEqual(resp2.status_code, status.HTTP_404_NOT_FOUND)
