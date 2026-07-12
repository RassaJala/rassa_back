from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from rassa.models import CategoriaProducto, Unidad


class CatalogCrudTestCase(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tester", password="secret123")
        self.client.force_authenticate(self.user)

    def _assert_success_envelope(self, response, *, status_code=status.HTTP_200_OK, message=None):
        self.assertEqual(response.status_code, status_code)
        body = response.json()
        self.assertIn("data", body)
        if message is not None:
            self.assertEqual(body.get("message"), message)
        return body["data"]


class CategoryCrudTests(CatalogCrudTestCase):
    def setUp(self):
        super().setUp()
        self.category = CategoriaProducto.objects.create(
            nombre="Frutas",
            descripcion="Productos frutales",
            estado=True,
        )

    def test_create_category(self):
        data = self._assert_success_envelope(
            self.client.post(
                reverse("categoria-producto-list"),
                {"nombre": "Verduras", "descripcion": "Productos verdes", "estado": True},
                format="json",
            ),
            status_code=status.HTTP_201_CREATED,
            message="Registro creado correctamente.",
        )
        self.assertEqual(data["nombre"], "Verduras")
        self.assertEqual(data["descripcion"], "Productos verdes")
        self.assertTrue(data["estado"])

    def test_list_categories(self):
        data = self._assert_success_envelope(self.client.get(reverse("categoria-producto-list")))
        self.assertGreaterEqual(len(data), 1)
        self.assertEqual(data[0]["nombre"], self.category.nombre)

    def test_retrieve_category(self):
        data = self._assert_success_envelope(
            self.client.get(reverse("categoria-producto-detail", args=[self.category.id_categoria]))
        )
        self.assertEqual(data["id_categoria"], self.category.id_categoria)
        self.assertEqual(data["nombre"], self.category.nombre)

    def test_update_category(self):
        data = self._assert_success_envelope(
            self.client.patch(
                reverse("categoria-producto-detail", args=[self.category.id_categoria]),
                {"nombre": "Frutas y Verduras"},
                format="json",
            ),
            message="Registro actualizado correctamente.",
        )
        self.assertEqual(data["nombre"], "Frutas y Verduras")

    def test_delete_category(self):
        response = self.client.delete(reverse("categoria-producto-detail", args=[self.category.id_categoria]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(CategoriaProducto.objects.filter(pk=self.category.id_categoria).exists())


class UnitCrudTests(CatalogCrudTestCase):
    def setUp(self):
        super().setUp()
        self.unit = Unidad.objects.create(
            nombre="Kilogramo",
            abreviatura="kg",
            tipo="Kilogramo",
            estado=True,
        )

    def test_create_unit(self):
        data = self._assert_success_envelope(
            self.client.post(
                reverse("unidad-list"),
                {"nombre": "Gramo", "abreviatura": "g", "estado": True},
                format="json",
            ),
            status_code=status.HTTP_201_CREATED,
            message="Registro creado correctamente.",
        )
        self.assertEqual(data["nombre"], "Gramo")
        self.assertEqual(data["abreviatura"], "g")

    def test_list_units(self):
        data = self._assert_success_envelope(self.client.get(reverse("unidad-list")))
        self.assertGreaterEqual(len(data), 1)
        self.assertEqual(data[0]["nombre"], self.unit.nombre)

    def test_retrieve_unit(self):
        data = self._assert_success_envelope(
            self.client.get(reverse("unidad-detail", args=[self.unit.id_unidad]))
        )
        self.assertEqual(data["id_unidad"], self.unit.id_unidad)
        self.assertEqual(data["abreviatura"], self.unit.abreviatura)

    def test_update_unit(self):
        data = self._assert_success_envelope(
            self.client.patch(
                reverse("unidad-detail", args=[self.unit.id_unidad]),
                {"abreviatura": "kgm"},
                format="json",
            ),
            message="Registro actualizado correctamente.",
        )
        self.assertEqual(data["abreviatura"], "kgm")

    def test_delete_unit(self):
        response = self.client.delete(reverse("unidad-detail", args=[self.unit.id_unidad]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Unidad.objects.filter(pk=self.unit.id_unidad).exists())


class CatalogAuthErrorTests(APITestCase):
    def test_categories_list_requires_auth(self):
        response = self.client.get(reverse("categoria-producto-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_categories_create_requires_auth(self):
        response = self.client.post(
            reverse("categoria-producto-list"),
            {"nombre": "Frutas", "descripcion": "Productos frutales"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_units_list_requires_auth(self):
        response = self.client.get(reverse("unidad-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_units_create_requires_auth(self):
        response = self.client.post(
            reverse("unidad-list"),
            {"nombre": "Kilogramo", "abreviatura": "kg"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class CatalogValidationErrorTests(CatalogCrudTestCase):
    def test_create_category_empty_payload(self):
        response = self.client.post(reverse("categoria-producto-list"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertIn("nombre", body)

    def test_create_category_missing_descripcion(self):
        response = self.client.post(
            reverse("categoria-producto-list"),
            {"nombre": "Frutas"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("descripcion", response.json())

    def test_create_category_nombre_too_long(self):
        response = self.client.post(
            reverse("categoria-producto-list"),
            {"nombre": "x" * 51, "descripcion": "Demasiado largo", "estado": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre", response.json())

    def test_create_unit_empty_payload(self):
        response = self.client.post(reverse("unidad-list"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertIn("nombre", body)
        self.assertIn("abreviatura", body)

    def test_create_unit_missing_abreviatura(self):
        response = self.client.post(
            reverse("unidad-list"),
            {"nombre": "Kilogramo"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("abreviatura", response.json())

    def test_create_unit_missing_nombre(self):
        response = self.client.post(
            reverse("unidad-list"),
            {"abreviatura": "kg"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre", response.json())

    def test_create_unit_abreviatura_too_long(self):
        response = self.client.post(
            reverse("unidad-list"),
            {"nombre": "Kilogramo", "abreviatura": "x" * 21, "estado": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("abreviatura", response.json())

    def test_create_unit_nombre_too_long(self):
        response = self.client.post(
            reverse("unidad-list"),
            {"nombre": "x" * 101, "abreviatura": "kg", "estado": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre", response.json())

    def test_retrieve_category_not_found(self):
        response = self.client.get(reverse("categoria-producto-detail", args=[99999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_unit_not_found(self):
        response = self.client.get(reverse("unidad-detail", args=[99999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
