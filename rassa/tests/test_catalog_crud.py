from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from rassa.models import CategoriaProducto, Persona, Producto, ProductoSemanal, PublicacionSemanal, Rol, Unidad, Usuario


def _create_user_with_role(nombre_rol, username):
    user = get_user_model().objects.create_user(username=username, password="secret123")
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
    Usuario.objects.create(
        fk_user=user,
        fk_persona=persona,
        telefono="1234567890",
        correo=f"{username}@rassa.com",
        fk_rol=rol,
    )
    return user


class CatalogCrudTestCase(APITestCase):
    def setUp(self):
        self.admin = _create_user_with_role("Administrador", "admin_tester")
        self.reader = _create_user_with_role("Cliente", "reader_tester")
        self.client.force_authenticate(self.admin)

    def _assert_success_envelope(self, response, *, status_code=status.HTTP_200_OK, message=None):
        self.assertEqual(response.status_code, status_code)
        body = response.json()
        self.assertIn("data", body)
        if message is not None:
            self.assertEqual(body.get("message"), message)
        return body["data"]

    def _assert_message_envelope(self, response, *, status_code=status.HTTP_200_OK, message=None):
        self.assertEqual(response.status_code, status_code)
        body = response.json()
        self.assertNotIn("data", body)
        if message is not None:
            self.assertEqual(body.get("message"), message)


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
        self.assertGreaterEqual(data["count"], 1)
        self.assertGreaterEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["nombre"], self.category.nombre)

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

    def test_delete_category_soft_deletes(self):
        self._assert_message_envelope(
            self.client.delete(reverse("categoria-producto-detail", args=[self.category.id_categoria])),
            message="Registro eliminado correctamente.",
        )
        self.category.refresh_from_db()
        self.assertFalse(self.category.estado)
        data = self._assert_success_envelope(self.client.get(reverse("categoria-producto-list")))
        ids = [item["id_categoria"] for item in data["results"]]
        self.assertNotIn(self.category.id_categoria, ids)

    def test_delete_category_with_linked_products_soft_deletes(self):
        Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.category,
            es_perecedero=True,
            estado=True,
        )
        self._assert_message_envelope(
            self.client.delete(reverse("categoria-producto-detail", args=[self.category.id_categoria])),
            message="Registro eliminado correctamente.",
        )
        self.category.refresh_from_db()
        self.assertFalse(self.category.estado)
        self.assertTrue(Producto.objects.filter(fk_categoria=self.category).exists())

    def test_create_category_ignores_client_supplied_id(self):
        data = self._assert_success_envelope(
            self.client.post(
                reverse("categoria-producto-list"),
                {
                    "id_categoria": 99999,
                    "nombre": "Verduras",
                    "descripcion": "Productos verdes",
                    "estado": True,
                },
                format="json",
            ),
            status_code=status.HTTP_201_CREATED,
            message="Registro creado correctamente.",
        )
        self.assertNotEqual(data["id_categoria"], 99999)


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

    def test_create_unit_syncs_tipo_from_nombre(self):
        self.client.post(
            reverse("unidad-list"),
            {"nombre": "Litro", "abreviatura": "L", "estado": True},
            format="json",
        )
        unit = Unidad.objects.get(nombre="Litro")
        self.assertEqual(unit.tipo, "Litro")

    def test_update_unit_syncs_tipo_when_nombre_changes(self):
        self.client.patch(
            reverse("unidad-detail", args=[self.unit.id_unidad]),
            {"nombre": "Mililitro"},
            format="json",
        )
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.nombre, "Mililitro")
        self.assertEqual(self.unit.tipo, "Mililitro")

    def test_list_units(self):
        data = self._assert_success_envelope(self.client.get(reverse("unidad-list")))
        self.assertGreaterEqual(data["count"], 1)
        self.assertGreaterEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["nombre"], self.unit.nombre)

    def test_retrieve_unit(self):
        data = self._assert_success_envelope(self.client.get(reverse("unidad-detail", args=[self.unit.id_unidad])))
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

    def test_delete_unit_soft_deletes(self):
        self._assert_message_envelope(
            self.client.delete(reverse("unidad-detail", args=[self.unit.id_unidad])),
            message="Registro eliminado correctamente.",
        )
        self.unit.refresh_from_db()
        self.assertFalse(self.unit.estado)
        data = self._assert_success_envelope(self.client.get(reverse("unidad-list")))
        ids = [item["id_unidad"] for item in data["results"]]
        self.assertNotIn(self.unit.id_unidad, ids)

    def test_delete_unit_with_linked_producto_semanal_soft_deletes(self):
        publicacion = PublicacionSemanal.objects.create(
            fecha_publicacion="2026-01-01",
            semana=1,
            estado="publicado",
        )
        producto = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=CategoriaProducto.objects.create(
                nombre="Frutas",
                descripcion="Productos frutales",
                estado=True,
            ),
            es_perecedero=True,
            estado=True,
        )
        ProductoSemanal.objects.create(
            fk_publicacion=publicacion,
            fk_producto=producto,
            fk_unidad=self.unit,
            stock=10,
            precio="25.00",
        )
        self._assert_message_envelope(
            self.client.delete(reverse("unidad-detail", args=[self.unit.id_unidad])),
            message="Registro eliminado correctamente.",
        )
        self.unit.refresh_from_db()
        self.assertFalse(self.unit.estado)
        self.assertTrue(ProductoSemanal.objects.filter(fk_unidad=self.unit).exists())

    def test_create_unit_ignores_client_supplied_id(self):
        data = self._assert_success_envelope(
            self.client.post(
                reverse("unidad-list"),
                {"id_unidad": 99999, "nombre": "Gramo", "abreviatura": "g", "estado": True},
                format="json",
            ),
            status_code=status.HTTP_201_CREATED,
            message="Registro creado correctamente.",
        )
        self.assertNotEqual(data["id_unidad"], 99999)


class CatalogAuthErrorTests(APITestCase):
    def setUp(self):
        self.category = CategoriaProducto.objects.create(
            nombre="Frutas",
            descripcion="Productos frutales",
            estado=True,
        )
        self.unit = Unidad.objects.create(
            nombre="Kilogramo",
            abreviatura="kg",
            tipo="Kilogramo",
            estado=True,
        )

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

    def test_categories_update_requires_auth(self):
        response = self.client.patch(
            reverse("categoria-producto-detail", args=[self.category.id_categoria]),
            {"nombre": "Nueva"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_categories_delete_requires_auth(self):
        response = self.client.delete(reverse("categoria-producto-detail", args=[self.category.id_categoria]))
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

    def test_units_update_requires_auth(self):
        response = self.client.patch(
            reverse("unidad-detail", args=[self.unit.id_unidad]),
            {"abreviatura": "kgm"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_units_delete_requires_auth(self):
        response = self.client.delete(reverse("unidad-detail", args=[self.unit.id_unidad]))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class CatalogPermissionErrorTests(CatalogCrudTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.reader)
        self.category = CategoriaProducto.objects.create(
            nombre="Frutas",
            descripcion="Productos frutales",
            estado=True,
        )
        self.unit = Unidad.objects.create(
            nombre="Kilogramo",
            abreviatura="kg",
            tipo="Kilogramo",
            estado=True,
        )

    def test_non_admin_can_list_categories(self):
        response = self.client.get(reverse("categoria-producto-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_admin_cannot_create_category(self):
        response = self.client.post(
            reverse("categoria-producto-list"),
            {"nombre": "Verduras", "descripcion": "Productos verdes", "estado": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_admin_cannot_update_category(self):
        response = self.client.patch(
            reverse("categoria-producto-detail", args=[self.category.id_categoria]),
            {"nombre": "Nueva"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_admin_cannot_delete_category(self):
        response = self.client.delete(reverse("categoria-producto-detail", args=[self.category.id_categoria]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_admin_cannot_create_unit(self):
        response = self.client.post(
            reverse("unidad-list"),
            {"nombre": "Gramo", "abreviatura": "g", "estado": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_admin_cannot_update_unit(self):
        response = self.client.patch(
            reverse("unidad-detail", args=[self.unit.id_unidad]),
            {"abreviatura": "kgm"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_admin_cannot_delete_unit(self):
        response = self.client.delete(reverse("unidad-detail", args=[self.unit.id_unidad]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CatalogValidationErrorTests(CatalogCrudTestCase):
    def setUp(self):
        super().setUp()
        self.category = CategoriaProducto.objects.create(
            nombre="Frutas",
            descripcion="Productos frutales",
            estado=True,
        )
        self.unit = Unidad.objects.create(
            nombre="Kilogramo",
            abreviatura="kg",
            tipo="Kilogramo",
            estado=True,
        )

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

    def test_update_category_nombre_too_long(self):
        response = self.client.patch(
            reverse("categoria-producto-detail", args=[self.category.id_categoria]),
            {"nombre": "x" * 51},
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

    def test_update_unit_abreviatura_too_long(self):
        response = self.client.patch(
            reverse("unidad-detail", args=[self.unit.id_unidad]),
            {"abreviatura": "x" * 21},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("abreviatura", response.json())

    def test_update_unit_nombre_too_long(self):
        response = self.client.patch(
            reverse("unidad-detail", args=[self.unit.id_unidad]),
            {"nombre": "x" * 101},
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
