from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from rassa.models import (
    CategoriaProducto,
    Persona,
    Producto,
    ProductoSemanal,
    PublicacionSemanal,
    Rol,
    Unidad,
    Usuario,
)


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


class PublicacionBaseTestCase(APITestCase):
    """Setup compartido para tests de publicaciones."""

    def setUp(self):
        self.agricultor = _create_user_with_role("Agricultor", "agricultor_test")
        self.cliente = _create_user_with_role("Cliente", "cliente_test")
        self.client.force_authenticate(self.agricultor)

        self.categoria = CategoriaProducto.objects.create(
            nombre="Frutas", descripcion="Frutas", estado=True
        )
        self.producto = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            es_perecedero=True,
            estado=True,
        )
        self.unidad = Unidad.objects.create(
            nombre="Kilogramo", abreviatura="kg", tipo="Kilogramo", estado=True
        )

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

    def _create_publicacion(self):
        response = self.client.post(reverse("publicacion-list"))
        return self._assert_success_envelope(
            response,
            status_code=status.HTTP_201_CREATED,
            message="Publicación creada correctamente.",
        )

    def _create_producto_semanal(self, publicacion_id, **overrides):
        defaults = {
            "fk_producto": self.producto.id_producto,
            "fk_unidad": self.unidad.id_unidad,
            "stock": 10,
            "precio": "25.00",
            "foto": "http://example.com/foto.jpg",
        }
        defaults.update(overrides)
        return self.client.post(
            reverse("producto-semanal-list", args=[publicacion_id]),
            defaults,
            format="json",
        )


# ======================================================================
# PUBLICACION — Auth & Permission
# ======================================================================


class PublicacionAuthTests(APITestCase):
    def test_list_requires_auth(self):
        response = self.client.get(reverse("publicacion-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_requires_auth(self):
        response = self.client.post(reverse("publicacion-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_requires_auth(self):
        response = self.client.get(reverse("publicacion-detail", args=[1]))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_partial_update_requires_auth(self):
        response = self.client.patch(
            reverse("publicacion-detail", args=[1]), {"estado": "publicado"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_destroy_requires_auth(self):
        response = self.client.delete(reverse("publicacion-detail", args=[1]))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_publish_requires_auth(self):
        response = self.client.post(reverse("publicacion-publish", args=[1]))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_close_requires_auth(self):
        response = self.client.post(reverse("publicacion-close", args=[1]))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PublicacionPermissionTests(PublicacionBaseTestCase):
    def setUp(self):
        super().setUp()
        pub_data = self._create_publicacion()
        self.pub_id = pub_data["id_publicacion"]
        self.client.force_authenticate(self.cliente)

    def test_non_agricultor_cannot_list(self):
        response = self.client.get(reverse("publicacion-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_agricultor_cannot_create(self):
        response = self.client.post(reverse("publicacion-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_agricultor_cannot_retrieve(self):
        response = self.client.get(reverse("publicacion-detail", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_agricultor_cannot_partial_update(self):
        response = self.client.patch(
            reverse("publicacion-detail", args=[self.pub_id]), {}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_agricultor_cannot_destroy(self):
        response = self.client.delete(reverse("publicacion-detail", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_agricultor_cannot_publish(self):
        response = self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_agricultor_cannot_close(self):
        response = self.client.post(reverse("publicacion-close", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ======================================================================
# PUBLICACION CRUD
# ======================================================================


class PublicacionCreateTests(PublicacionBaseTestCase):
    def test_create_publicacion(self):
        data = self._assert_success_envelope(
            self.client.post(reverse("publicacion-list")),
            status_code=status.HTTP_201_CREATED,
            message="Publicación creada correctamente.",
        )
        self.assertIn("id_publicacion", data)
        self.assertEqual(data["estado"], "borrador")
        self.assertEqual(data["productos"], [])
        self.assertIn("fk_agricultor", data)


class PublicacionListTests(PublicacionBaseTestCase):
    def setUp(self):
        super().setUp()
        self.pub1 = self._create_publicacion()
        self.pub2 = self._create_publicacion()

    def test_list_publicaciones(self):
        data = self._assert_success_envelope(self.client.get(reverse("publicacion-list")))
        self.assertIn("count", data)
        self.assertIn("results", data)
        self.assertGreaterEqual(data["count"], 2)

    def test_list_filter_by_estado(self):
        pub = PublicacionSemanal.objects.get(pk=self.pub1["id_publicacion"])
        pub.estado = "publicado"
        pub.save(update_fields=["estado"])

        data = self._assert_success_envelope(
            self.client.get(reverse("publicacion-list"), {"estado": "publicado"})
        )
        for item in data["results"]:
            self.assertEqual(item["estado"], "publicado")

        data = self._assert_success_envelope(
            self.client.get(reverse("publicacion-list"), {"estado": "borrador"})
        )
        for item in data["results"]:
            self.assertEqual(item["estado"], "borrador")


class PublicacionRetrieveTests(PublicacionBaseTestCase):
    def setUp(self):
        super().setUp()
        self.pub_data = self._create_publicacion()
        self.pub_id = self.pub_data["id_publicacion"]

    def test_retrieve_publicacion(self):
        data = self._assert_success_envelope(
            self.client.get(reverse("publicacion-detail", args=[self.pub_id]))
        )
        self.assertEqual(data["id_publicacion"], self.pub_id)
        self.assertEqual(data["estado"], "borrador")

    def test_retrieve_non_existent_returns_404(self):
        response = self.client.get(reverse("publicacion-detail", args=[99999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_other_agricultor_publicacion_returns_404(self):
        otro = _create_user_with_role("Agricultor", "otro_agricultor")
        self.client.force_authenticate(otro)
        response = self.client.get(reverse("publicacion-detail", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PublicacionPartialUpdateTests(PublicacionBaseTestCase):
    def setUp(self):
        super().setUp()
        self.pub_data = self._create_publicacion()
        self.pub_id = self.pub_data["id_publicacion"]

    def test_partial_update_draft_returns_data(self):
        data = self._assert_success_envelope(
            self.client.patch(
                reverse("publicacion-detail", args=[self.pub_id]),
                {},
                format="json",
            ),
            message="Publicación actualizada correctamente.",
        )
        self.assertEqual(data["id_publicacion"], self.pub_id)

    def test_partial_update_published_returns_400(self):
        pub = PublicacionSemanal.objects.get(pk=self.pub_id)
        pub.estado = "publicado"
        pub.save(update_fields=["estado"])

        response = self.client.patch(
            reverse("publicacion-detail", args=[self.pub_id]),
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_partial_update_cerrado_returns_400(self):
        pub = PublicacionSemanal.objects.get(pk=self.pub_id)
        pub.estado = "cerrado"
        pub.save(update_fields=["estado"])

        response = self.client.patch(
            reverse("publicacion-detail", args=[self.pub_id]),
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PublicacionDeleteTests(PublicacionBaseTestCase):
    def setUp(self):
        super().setUp()
        self.pub_data = self._create_publicacion()
        self.pub_id = self.pub_data["id_publicacion"]

    def test_delete_draft_returns_200(self):
        self._assert_message_envelope(
            self.client.delete(reverse("publicacion-detail", args=[self.pub_id])),
            message="Publicación eliminada correctamente.",
        )
        self.assertFalse(
            PublicacionSemanal.objects.filter(pk=self.pub_id).exists()
        )

    def test_delete_published_returns_400(self):
        pub = PublicacionSemanal.objects.get(pk=self.pub_id)
        pub.estado = "publicado"
        pub.save(update_fields=["estado"])

        response = self.client.delete(reverse("publicacion-detail", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_cerrado_returns_400(self):
        pub = PublicacionSemanal.objects.get(pk=self.pub_id)
        pub.estado = "cerrado"
        pub.save(update_fields=["estado"])

        response = self.client.delete(reverse("publicacion-detail", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_non_existent_returns_404(self):
        response = self.client.delete(reverse("publicacion-detail", args=[99999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ======================================================================
# PUBLICACION — Publish / Close workflow
# ======================================================================


class PublicacionPublishTests(PublicacionBaseTestCase):
    def setUp(self):
        super().setUp()
        self.pub_data = self._create_publicacion()
        self.pub_id = self.pub_data["id_publicacion"]

    def test_publish_without_productos_returns_400(self):
        response = self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.json())

    def test_publish_with_valid_productos_returns_200(self):
        self._create_producto_semanal(self.pub_id)
        data = self._assert_success_envelope(
            self.client.post(reverse("publicacion-publish", args=[self.pub_id])),
            message="Publicación publicada correctamente.",
        )
        self.assertEqual(data["estado"], "publicado")

    def _add_producto_directo(self, **overrides):
        defaults = {
            "fk_publicacion_id": self.pub_id,
            "fk_producto": self.producto,
            "fk_unidad": self.unidad,
            "stock": 10,
            "precio": "25.00",
            "foto": "http://example.com/foto.jpg",
            "estado": "activo",
        }
        defaults.update(overrides)
        return ProductoSemanal.objects.create(**defaults)

    def test_publish_validates_stock(self):
        self._add_producto_directo(stock=0)
        response = self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertIn("productos", body)
        self.assertIn("stock", body["productos"][0])

    def test_publish_validates_precio(self):
        self._add_producto_directo(precio="0.00")
        response = self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertIn("productos", body)
        self.assertIn("precio", body["productos"][0])

    def test_publish_validates_negative_precio(self):
        self._add_producto_directo(precio="-1.00")
        response = self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertIn("productos", body)

    def test_publish_validates_empty_foto(self):
        self._add_producto_directo(foto="")
        response = self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertIn("productos", body)
        self.assertIn("foto", body["productos"][0])

    def test_publish_validates_null_foto(self):
        self._add_producto_directo(foto=None)
        response = self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertIn("productos", body)

    def test_publish_already_published_returns_400(self):
        self._create_producto_semanal(self.pub_id)
        self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        response = self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_publish_only_checks_active_productos(self):
        pub = PublicacionSemanal.objects.get(pk=self.pub_id)
        ProductoSemanal.objects.create(
            fk_publicacion=pub,
            fk_producto=self.producto,
            fk_unidad=self.unidad,
            stock=10,
            precio="25.00",
            foto="http://example.com/foto.jpg",
            estado="inactivo",
        )
        response = self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_publish_non_existent_returns_404(self):
        response = self.client.post(reverse("publicacion-publish", args=[99999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PublicacionCloseTests(PublicacionBaseTestCase):
    def setUp(self):
        super().setUp()
        self.pub_data = self._create_publicacion()
        self.pub_id = self.pub_data["id_publicacion"]

    def test_close_draft_returns_400(self):
        response = self.client.post(reverse("publicacion-close", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_close_published_returns_200(self):
        self._create_producto_semanal(self.pub_id)
        self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        data = self._assert_success_envelope(
            self.client.post(reverse("publicacion-close", args=[self.pub_id])),
            message="Publicación cerrada correctamente.",
        )
        self.assertEqual(data["estado"], "cerrado")

    def test_close_cerrado_returns_400(self):
        self._create_producto_semanal(self.pub_id)
        self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        self.client.post(reverse("publicacion-close", args=[self.pub_id]))
        response = self.client.post(reverse("publicacion-close", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_close_non_existent_returns_404(self):
        response = self.client.post(reverse("publicacion-close", args=[99999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ======================================================================
# PRODUCTO SEMANAL — Auth & Permission
# ======================================================================


class ProductoSemanalAuthTests(APITestCase):
    def test_list_requires_auth(self):
        response = self.client.get(reverse("producto-semanal-list", args=[1]))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_requires_auth(self):
        response = self.client.post(reverse("producto-semanal-list", args=[1]), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_partial_update_requires_auth(self):
        response = self.client.patch(
            reverse("producto-semanal-detail", args=[1, 1]), {}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_destroy_requires_auth(self):
        response = self.client.delete(reverse("producto-semanal-detail", args=[1, 1]))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ======================================================================
# PRODUCTO SEMANAL CRUD
# ======================================================================


class ProductoSemanalCreateTests(PublicacionBaseTestCase):
    def setUp(self):
        super().setUp()
        self.pub_data = self._create_publicacion()
        self.pub_id = self.pub_data["id_publicacion"]

    def test_create_producto_returns_201(self):
        data = self._assert_success_envelope(
            self._create_producto_semanal(self.pub_id),
            status_code=status.HTTP_201_CREATED,
            message="Producto agregado correctamente.",
        )
        self.assertEqual(data["stock"], 10)
        self.assertEqual(str(data["precio"]), "25.00")
        self.assertEqual(data["estado"], "activo")
        self.assertIn("id_producto_semanal", data)

    def test_create_producto_in_published_returns_400(self):
        self._create_producto_semanal(self.pub_id)
        self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        response = self._create_producto_semanal(self.pub_id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_producto_in_cerrado_returns_400(self):
        self._create_producto_semanal(self.pub_id)
        self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        self.client.post(reverse("publicacion-close", args=[self.pub_id]))
        response = self._create_producto_semanal(self.pub_id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_producto_non_existent_publicacion_returns_404(self):
        response = self._create_producto_semanal(99999)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_producto_from_other_agricultor_returns_404(self):
        otro = _create_user_with_role("Agricultor", "otro_agricultor")
        self.client.force_authenticate(otro)
        response = self._create_producto_semanal(self.pub_id)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_producto_validates_stock_zero(self):
        response = self._create_producto_semanal(self.pub_id, stock=0)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_producto_validates_stock_negative(self):
        response = self._create_producto_semanal(self.pub_id, stock=-1)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_producto_validates_precio_zero(self):
        response = self._create_producto_semanal(self.pub_id, precio="0.00")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_producto_validates_precio_negative(self):
        response = self._create_producto_semanal(self.pub_id, precio="-1.00")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ProductoSemanalListTests(PublicacionBaseTestCase):
    def setUp(self):
        super().setUp()
        self.pub_data = self._create_publicacion()
        self.pub_id = self.pub_data["id_publicacion"]
        self._create_producto_semanal(self.pub_id)
        self._create_producto_semanal(self.pub_id, stock=5, precio="30.00")

    def test_list_productos(self):
        data = self._assert_success_envelope(
            self.client.get(reverse("producto-semanal-list", args=[self.pub_id]))
        )
        self.assertEqual(len(data), 2)

    def test_list_only_active(self):
        pub = PublicacionSemanal.objects.get(pk=self.pub_id)
        item = pub.productosemanal_set.first()
        item.estado = "inactivo"
        item.save(update_fields=["estado"])
        data = self._assert_success_envelope(
            self.client.get(reverse("producto-semanal-list", args=[self.pub_id]))
        )
        self.assertEqual(len(data), 1)

    def test_list_non_existent_publicacion_returns_404(self):
        response = self.client.get(reverse("producto-semanal-list", args=[99999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ProductoSemanalUpdateTests(PublicacionBaseTestCase):
    def setUp(self):
        super().setUp()
        self.pub_data = self._create_publicacion()
        self.pub_id = self.pub_data["id_publicacion"]
        data = self._assert_success_envelope(
            self._create_producto_semanal(self.pub_id),
            status_code=status.HTTP_201_CREATED,
        )
        self.item_id = data["id_producto_semanal"]

    def test_partial_update_producto_returns_200(self):
        data = self._assert_success_envelope(
            self.client.patch(
                reverse("producto-semanal-detail", args=[self.pub_id, self.item_id]),
                {"stock": 20},
                format="json",
            ),
            message="Producto actualizado correctamente.",
        )
        self.assertEqual(data["stock"], 20)

    def test_partial_update_in_published_returns_400(self):
        self._create_producto_semanal(self.pub_id)
        self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        response = self.client.patch(
            reverse("producto-semanal-detail", args=[self.pub_id, self.item_id]),
            {"stock": 20},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_partial_update_non_existent_returns_404(self):
        response = self.client.patch(
            reverse("producto-semanal-detail", args=[self.pub_id, 99999]),
            {"stock": 20},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ProductoSemanalDeleteTests(PublicacionBaseTestCase):
    def setUp(self):
        super().setUp()
        self.pub_data = self._create_publicacion()
        self.pub_id = self.pub_data["id_publicacion"]
        data = self._assert_success_envelope(
            self._create_producto_semanal(self.pub_id),
            status_code=status.HTTP_201_CREATED,
        )
        self.item_id = data["id_producto_semanal"]

    def test_delete_producto_soft_deletes(self):
        self._assert_message_envelope(
            self.client.delete(
                reverse("producto-semanal-detail", args=[self.pub_id, self.item_id])
            ),
            message="Producto eliminado correctamente.",
        )
        item = ProductoSemanal.objects.get(pk=self.item_id)
        self.assertEqual(item.estado, "inactivo")

    def test_delete_producto_in_published_returns_400(self):
        self._create_producto_semanal(self.pub_id)
        self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        response = self.client.delete(
            reverse("producto-semanal-detail", args=[self.pub_id, self.item_id])
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_non_existent_returns_404(self):
        response = self.client.delete(
            reverse("producto-semanal-detail", args=[self.pub_id, 99999])
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
