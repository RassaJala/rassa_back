import base64

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from rassa.models import CategoriaProducto, Producto, ProductoImagen, Unidad, Usuario

TEST_MEDIA = "/tmp/rassa_test_media"


def _create_user_with_role(nombre_rol, username):
    user = get_user_model().objects.create_user(username=username, password="secret123")
    from rassa.models import Persona, Rol

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


def _small_gif():
    return (
        b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
        b"\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00"
        b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
        b"\x44\x01\x00\x3b"
    )


def _small_png():
    import io

    try:
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (1, 1), "red").save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01"
            b"\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class ProductoCRUDTests(TestCase):
    def setUp(self):
        self.admin = _create_user_with_role("Admin", "admin_producto")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.categoria = CategoriaProducto.objects.create(
            nombre="Frutas",
            descripcion="Productos frutales",
            estado=True,
        )
        self.unidad = Unidad.objects.create(
            nombre="Kilogramo",
            abreviatura="kg",
            tipo="peso",
            estado=True,
        )

    def test_create_producto(self):
        response = self.client.post(
            reverse("producto_list"),
            {
                "nombre_producto": "Manzana",
                "descripcion": "Manzana roja",
                "precio": "15.50",
                "stock": 100,
                "fk_categoria": self.categoria.id_categoria,
                "fk_unidad": self.unidad.id_unidad,
                "es_perecedero": True,
                "estado": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertIn("data", body)
        self.assertEqual(body["message"], "Producto creado exitosamente.")
        data = body["data"]
        self.assertEqual(data["nombre_producto"], "Manzana")
        self.assertEqual(data["precio"], "15.50")
        self.assertEqual(data["stock"], 100)

    def test_create_producto_missing_required_fields(self):
        response = self.client.post(reverse("producto_list"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_producto_negative_precio(self):
        response = self.client.post(
            reverse("producto_list"),
            {
                "nombre_producto": "Manzana",
                "precio": "-1",
                "fk_categoria": self.categoria.id_categoria,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_producto_negative_stock(self):
        response = self.client.post(
            reverse("producto_list"),
            {
                "nombre_producto": "Manzana",
                "precio": "10",
                "stock": -1,
                "fk_categoria": self.categoria.id_categoria,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_productos(self):
        Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            precio=15.50,
            stock=100,
        )
        response = self.client.get(reverse("producto_list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertGreaterEqual(len(data), 1)

    def test_retrieve_producto(self):
        p = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            precio=15.50,
        )
        response = self.client.get(reverse("producto_detail", args=[p.id_producto]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertEqual(data["nombre_producto"], "Manzana")

    def test_retrieve_producto_not_found(self):
        response = self.client.get(reverse("producto_detail", args=[99999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_producto(self):
        p = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            precio=15.50,
        )
        response = self.client.patch(
            reverse("producto_detail", args=[p.id_producto]),
            {"nombre_producto": "Manzana Gala"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertEqual(data["nombre_producto"], "Manzana Gala")

    def test_delete_producto(self):
        p = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
        )
        response = self.client.delete(reverse("producto_detail", args=[p.id_producto]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["message"], "Producto eliminado exitosamente.")
        p.refresh_from_db()
        self.assertFalse(p.estado)

    def test_non_admin_cannot_create_producto(self):
        reader = _create_user_with_role("Cliente", "reader_producto")
        self.client.force_authenticate(reader)
        response = self.client.post(
            reverse("producto_list"),
            {
                "nombre_producto": "Manzana",
                "precio": "10",
                "fk_categoria": self.categoria.id_categoria,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_list_productos(self):
        self.client.force_authenticate(None)
        response = self.client.get(reverse("producto_list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class ProductoImagenTests(TestCase):
    def setUp(self):
        self.admin = _create_user_with_role("Admin", "admin_img")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.categoria = CategoriaProducto.objects.create(nombre="Frutas", descripcion="Test", estado=True)
        self.producto = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            precio=15.50,
        )

    def test_upload_imagen_file(self):
        img = SimpleUploadedFile("test.gif", _small_gif(), content_type="image/gif")
        response = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen": img, "es_principal": "true"},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()["data"]
        self.assertTrue(data["es_principal"])
        self.assertIn("/media/productos/", data["url"])

    def test_upload_imagen_base64(self):
        b64 = base64.b64encode(_small_png()).decode()
        response = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen_base64": b64, "es_principal": "true"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_upload_rejects_non_image(self):
        fake = SimpleUploadedFile("test.txt", b"not an image", content_type="text/plain")
        response = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen": fake},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_rejects_disallowed_extension(self):
        img = SimpleUploadedFile("test.php", b"\x89PNG\r\n", content_type="image/png")
        response = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen": img},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_no_file_returns_400(self):
        response = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_to_nonexistent_producto(self):
        response = self.client.post(
            reverse("producto_imagen", args=[99999]),
            {},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_imagen(self):
        img = SimpleUploadedFile("test.gif", _small_gif(), content_type="image/gif")
        upload_resp = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen": img, "es_principal": "true"},
        )
        img_id = upload_resp.json()["data"]["id_imagen"]
        response = self.client.delete(reverse("producto_imagen_delete", args=[self.producto.id_producto, img_id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(ProductoImagen.objects.filter(id_imagen=img_id).exists())

    def test_patch_imagen_set_principal(self):
        img = SimpleUploadedFile("test.gif", _small_gif(), content_type="image/gif")
        upload_resp = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen": img, "es_principal": "false"},
        )
        img_id = upload_resp.json()["data"]["id_imagen"]
        response = self.client.patch(
            reverse("producto_imagen_delete", args=[self.producto.id_producto, img_id]),
            {"es_principal": "true"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.producto.refresh_from_db()
        self.assertIsNotNone(self.producto.imagen)

    def test_patch_imagen_no_changes(self):
        img = SimpleUploadedFile("test.gif", _small_gif(), content_type="image/gif")
        upload_resp = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen": img, "es_principal": "true"},
        )
        img_id = upload_resp.json()["data"]["id_imagen"]
        response = self.client.patch(
            reverse("producto_imagen_delete", args=[self.producto.id_producto, img_id]),
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["message"], "No se proporcionaron cambios.")

    def test_imagen_read_only_in_serializer(self):
        response = self.client.post(
            reverse("producto_list"),
            {
                "nombre_producto": "Manzana",
                "precio": "10",
                "fk_categoria": self.categoria.id_categoria,
                "imagen": "http://evil.com/hack.jpg",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.json()["data"]["imagen"])
