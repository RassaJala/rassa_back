from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from rassa.models import CategoriaProducto, Persona, Producto, ProductoImagen, Rol, Usuario


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


class ProductoImagenCrudTests(APITestCase):
    def setUp(self):
        self.admin = _create_user_with_role("Admin", "admin_img")
        self.reader = _create_user_with_role("Cliente", "reader_img")
        self.category = CategoriaProducto.objects.create(
            nombre="Frutas",
            descripcion="Productos frutales",
            estado=True,
        )
        self.producto = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.category,
            es_perecedero=True,
            estado=True,
        )
        self.imagen = ProductoImagen.objects.create(
            fk_producto=self.producto,
            url="https://example.com/manzana.jpg",
            es_principal=True,
            orden=1,
        )
        self.client.force_authenticate(self.admin)

    def _assert_success_envelope(self, response, *, status_code=status.HTTP_200_OK, message=None):
        self.assertEqual(response.status_code, status_code)
        body = response.json()
        self.assertIn("data", body)
        if message is not None:
            self.assertEqual(body.get("message"), message)
        return body["data"]

    # ── LIST ──────────────────────────────────────────────────────

    def test_list_imagenes_por_producto(self):
        response = self.client.get(reverse("producto-imagen-list", args=[self.producto.id_producto]))
        data = self._assert_success_envelope(response)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["url"], "https://example.com/manzana.jpg")

    def test_list_imagenes_producto_inexistente_returns_404(self):
        response = self.client.get(reverse("producto-imagen-list", args=[9999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ── CREATE ────────────────────────────────────────────────────

    def test_create_imagen_returns_201(self):
        response = self.client.post(
            reverse("producto-imagen-list", args=[self.producto.id_producto]),
            {"url": "https://example.com/manzana2.jpg", "orden": 2},
            format="json",
        )
        data = self._assert_success_envelope(
            response,
            status_code=status.HTTP_201_CREATED,
            message="Imagen registrada correctamente.",
        )
        self.assertEqual(data["url"], "https://example.com/manzana2.jpg")
        self.assertFalse(data["es_principal"])
        self.assertEqual(data["orden"], 2)

    def test_create_imagen_url_vacia_returns_400(self):
        response = self.client.post(
            reverse("producto-imagen-list", args=[self.producto.id_producto]),
            {"url": ""},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_imagen_url_spaces_returns_400(self):
        response = self.client.post(
            reverse("producto-imagen-list", args=[self.producto.id_producto]),
            {"url": "   "},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_imagen_es_principal_false_by_default(self):
        response = self.client.post(
            reverse("producto-imagen-list", args=[self.producto.id_producto]),
            {"url": "https://example.com/test.jpg"},
            format="json",
        )
        data = self._assert_success_envelope(response, status_code=status.HTTP_201_CREATED)
        self.assertFalse(data["es_principal"])

    # ── DELETE ────────────────────────────────────────────────────

    def test_delete_imagen(self):
        response = self.client.delete(
            reverse("producto-imagen-detail", args=[self.producto.id_producto, self.imagen.id_imagen])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body.get("message"), "Imagen eliminada correctamente.")
        self.assertFalse(ProductoImagen.objects.filter(pk=self.imagen.id_imagen).exists())

    def test_delete_imagen_inexistente_returns_404(self):
        response = self.client.delete(reverse("producto-imagen-detail", args=[self.producto.id_producto, 9999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_imagen_de_otro_producto_returns_404(self):
        otro_producto = Producto.objects.create(
            nombre_producto="Pera",
            fk_categoria=self.category,
            estado=True,
        )
        response = self.client.delete(
            reverse("producto-imagen-detail", args=[otro_producto.id_producto, self.imagen.id_imagen])
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ── SET PRINCIPAL ─────────────────────────────────────────────

    def test_set_principal_marca_como_principal(self):
        img2 = ProductoImagen.objects.create(
            fk_producto=self.producto,
            url="https://example.com/manzana2.jpg",
            es_principal=False,
            orden=2,
        )
        response = self.client.patch(
            reverse("producto-imagen-set-principal", args=[self.producto.id_producto, img2.id_imagen])
        )
        data = self._assert_success_envelope(response, message="Imagen marcada como principal.")
        self.assertTrue(data["es_principal"])
        # Verificar que la anterior ya no es principal
        self.imagen.refresh_from_db()
        self.assertFalse(self.imagen.es_principal)

    def test_set_principal_desmarca_antes(self):
        """Solo queda una principal por producto."""
        img2 = ProductoImagen.objects.create(
            fk_producto=self.producto,
            url="https://example.com/manzana2.jpg",
            es_principal=False,
            orden=2,
        )
        img3 = ProductoImagen.objects.create(
            fk_producto=self.producto,
            url="https://example.com/manzana3.jpg",
            es_principal=False,
            orden=3,
        )
        # Marcar img2 como principal
        self.client.patch(reverse("producto-imagen-set-principal", args=[self.producto.id_producto, img2.id_imagen]))
        # Marcar img3 como principal
        self.client.patch(reverse("producto-imagen-set-principal", args=[self.producto.id_producto, img3.id_imagen]))
        # Solo img3 debe ser principal
        self.assertEqual(
            ProductoImagen.objects.filter(fk_producto=self.producto, es_principal=True).count(),
            1,
        )
        img3.refresh_from_db()
        self.assertTrue(img3.es_principal)

    def test_set_principal_imagen_inexistente_returns_404(self):
        response = self.client.patch(reverse("producto-imagen-set-principal", args=[self.producto.id_producto, 9999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ── PERMISSIONS ───────────────────────────────────────────────

    def test_no_puede_crear_imagen_sin_auth(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            reverse("producto-imagen-list", args=[self.producto.id_producto]),
            {"url": "https://example.com/test.jpg"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_reader_no_puede_crear_imagen(self):
        self.client.force_authenticate(self.reader)
        response = self.client.post(
            reverse("producto-imagen-list", args=[self.producto.id_producto]),
            {"url": "https://example.com/test.jpg"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_reader_puede_listar_imagenes(self):
        self.client.force_authenticate(self.reader)
        response = self.client.get(reverse("producto-imagen-list", args=[self.producto.id_producto]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_reader_no_puede_eliminar_imagen(self):
        self.client.force_authenticate(self.reader)
        response = self.client.delete(
            reverse("producto-imagen-detail", args=[self.producto.id_producto, self.imagen.id_imagen])
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_reader_no_puede_marcar_principal(self):
        self.client.force_authenticate(self.reader)
        response = self.client.patch(
            reverse("producto-imagen-set-principal", args=[self.producto.id_producto, self.imagen.id_imagen])
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
