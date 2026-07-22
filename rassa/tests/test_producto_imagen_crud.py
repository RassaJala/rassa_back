from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from rassa.blueprints.producto_imagen.serializers import ProductoImagenSerializer
from rassa.models import (
    CategoriaProducto,
    Persona,
    Producto,
    ProductoImagen,
    ProductoSemanal,
    PublicacionSemanal,
    Rol,
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

    def test_create_imagen_http_url_rejected(self):
        response = self.client.post(
            reverse("producto-imagen-list", args=[self.producto.id_producto]),
            {"url": "http://example.com/test.jpg"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_imagen_javascript_url_rejected(self):
        response = self.client.post(
            reverse("producto-imagen-list", args=[self.producto.id_producto]),
            {"url": "javascript:alert(1)"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_imagen_data_url_rejected(self):
        response = self.client.post(
            reverse("producto-imagen-list", args=[self.producto.id_producto]),
            {"url": "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg=="},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_imagen_returns_drive_file_id(self):
        response = self.client.post(
            reverse("producto-imagen-list", args=[self.producto.id_producto]),
            {"url": "https://example.com/test.jpg"},
            format="json",
        )
        data = self._assert_success_envelope(response, status_code=status.HTTP_201_CREATED)
        self.assertIn("drive_file_id", data)

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

    # ── PARTIAL UPDATE (PATCH) ───────────────────────────────────

    def test_patch_actualiza_url(self):
        response = self.client.patch(
            reverse("producto-imagen-detail", args=[self.producto.id_producto, self.imagen.id_imagen]),
            {"url": "https://example.com/nueva-manzana.jpg"},
            format="json",
        )
        data = self._assert_success_envelope(response, message="Imagen actualizada correctamente.")
        self.assertEqual(data["url"], "https://example.com/nueva-manzana.jpg")
        self.imagen.refresh_from_db()
        self.assertEqual(self.imagen.url, "https://example.com/nueva-manzana.jpg")

    def test_patch_actualiza_orden(self):
        response = self.client.patch(
            reverse("producto-imagen-detail", args=[self.producto.id_producto, self.imagen.id_imagen]),
            {"orden": 99},
            format="json",
        )
        data = self._assert_success_envelope(response, message="Imagen actualizada correctamente.")
        self.assertEqual(data["orden"], 99)

    def test_patch_actualiza_url_y_orden_simultaneamente(self):
        response = self.client.patch(
            reverse("producto-imagen-detail", args=[self.producto.id_producto, self.imagen.id_imagen]),
            {"url": "https://example.com/updated.jpg", "orden": 5},
            format="json",
        )
        data = self._assert_success_envelope(response, message="Imagen actualizada correctamente.")
        self.assertEqual(data["url"], "https://example.com/updated.jpg")
        self.assertEqual(data["orden"], 5)

    def test_patch_campos_no_permitidos_ignorados(self):
        self.imagen.es_principal = True
        self.imagen.save(update_fields=["es_principal"])
        response = self.client.patch(
            reverse("producto-imagen-detail", args=[self.producto.id_producto, self.imagen.id_imagen]),
            {"es_principal": False, "url": "https://example.com/test.jpg"},
            format="json",
        )
        self._assert_success_envelope(response, message="Imagen actualizada correctamente.")
        self.imagen.refresh_from_db()
        self.assertTrue(self.imagen.es_principal)

    def test_patch_sin_campos_validos_returns_400(self):
        response = self.client.patch(
            reverse("producto-imagen-detail", args=[self.producto.id_producto, self.imagen.id_imagen]),
            {"campo_invalido": "valor"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_url_inexistente_returns_404(self):
        response = self.client.patch(
            reverse("producto-imagen-detail", args=[self.producto.id_producto, 9999]),
            {"url": "https://example.com/test.jpg"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_url_http_rejected(self):
        response = self.client.patch(
            reverse("producto-imagen-detail", args=[self.producto.id_producto, self.imagen.id_imagen]),
            {"url": "http://example.com/test.jpg"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reader_no_puede_parchar_imagen(self):
        self.client.force_authenticate(self.reader)
        response = self.client.patch(
            reverse("producto-imagen-detail", args=[self.producto.id_producto, self.imagen.id_imagen]),
            {"url": "https://example.com/test.jpg"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ── OWNERSHIP ────────────────────────────────────────────────

    def test_agricultor_con_publicacion_puede_crear_imagen(self):
        agricultor = _create_user_with_role("Agricultor", "agri_owner")
        publicacion = PublicacionSemanal.objects.create(
            fk_agricultor=agricultor.usuario,
            fecha_publicacion="2026-07-21",
            semana=29,
            estado="publicado",
        )
        from rassa.models import Unidad

        unidad, _ = Unidad.objects.get_or_create(
            tipo="Peso",
            defaults={"nombre": "Kilogramo", "abreviatura": "kg"},
        )
        ProductoSemanal.objects.create(
            fk_publicacion=publicacion,
            fk_producto=self.producto,
            fk_unidad=unidad,
            stock=10,
            precio=25.00,
        )
        self.client.force_authenticate(agricultor)
        response = self.client.post(
            reverse("producto-imagen-list", args=[self.producto.id_producto]),
            {"url": "https://example.com/agri.jpg"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_agricultor_sin_publicacion_no_puede_crear_imagen(self):
        agricultor = _create_user_with_role("Agricultor", "agri_no_pub")
        self.client.force_authenticate(agricultor)
        response = self.client.post(
            reverse("producto-imagen-list", args=[self.producto.id_producto]),
            {"url": "https://example.com/test.jpg"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_agricultor_sin_publicacion_no_puede_eliminar_imagen(self):
        agricultor = _create_user_with_role("Agricultor", "agri_del")
        self.client.force_authenticate(agricultor)
        response = self.client.delete(
            reverse("producto-imagen-detail", args=[self.producto.id_producto, self.imagen.id_imagen])
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_agricultor_sin_publicacion_no_puede_parchar_imagen(self):
        agricultor = _create_user_with_role("Agricultor", "agri_patch")
        self.client.force_authenticate(agricultor)
        response = self.client.patch(
            reverse("producto-imagen-detail", args=[self.producto.id_producto, self.imagen.id_imagen]),
            {"url": "https://example.com/new.jpg"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_agricultor_sin_publicacion_no_puede_set_principal(self):
        agricultor = _create_user_with_role("Agricultor", "agri_principal")
        self.client.force_authenticate(agricultor)
        response = self.client.patch(
            reverse("producto-imagen-set-principal", args=[self.producto.id_producto, self.imagen.id_imagen])
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_puede_parchar_imagen_de_cualquier_producto(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            reverse("producto-imagen-detail", args=[self.producto.id_producto, self.imagen.id_imagen]),
            {"url": "https://example.com/admin-update.jpg"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ── INTEGRATION: FILE UPLOAD (CRÍTICO 4 y 5) ─────────────────

    def test_upload_archivo_returns_201_y_persiste_drive_file_id(self):
        """CRÍTICO 4: Test de integración — upload multipart vía endpoint HTTP."""
        fake_image = SimpleUploadedFile(
            "tomate.jpg",
            b"\xff\xd8\xff\xe0" + b"\x00" * 1024,
            content_type="image/jpeg",
        )
        with patch("rassa.blueprints.producto_imagen.views.upload_image") as mock_upload:
            mock_upload.return_value = {
                "url": "https://drive.google.com/uc?id=abc123&export=download",
                "file_id": "abc123",
            }
            response = self.client.post(
                reverse("producto-imagen-list", args=[self.producto.id_producto]),
                {"archivo": fake_image},
            )
        data = self._assert_success_envelope(
            response,
            status_code=status.HTTP_201_CREATED,
            message="Imagen registrada correctamente.",
        )
        self.assertEqual(data["url"], "https://drive.google.com/uc?id=abc123&export=download")
        self.assertEqual(data["drive_file_id"], "abc123")
        imagen = ProductoImagen.objects.get(pk=data["id_imagen"])
        self.assertEqual(imagen.drive_file_id, "abc123")

    def test_upload_archivo_502_on_drive_error(self):
        """CRÍTICO 5: Error de Drive retorna 502 desde el endpoint HTTP."""
        fake_image = SimpleUploadedFile(
            "tomate.jpg",
            b"\xff\xd8\xff\xe0" + b"\x00" * 1024,
            content_type="image/jpeg",
        )
        with patch("rassa.blueprints.producto_imagen.views.upload_image") as mock_upload:
            mock_upload.side_effect = RuntimeError("Drive API unavailable")
            response = self.client.post(
                reverse("producto-imagen-list", args=[self.producto.id_producto]),
                {"archivo": fake_image},
            )
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        body = response.json()
        self.assertIn("Google Drive", body.get("message", ""))

    def test_upload_archivo_value_error_returns_400(self):
        """Error de validación de archivo retorna 400."""
        fake_image = SimpleUploadedFile(
            "tomate.exe",
            b"\x00" * 100,
            content_type="application/exe",
        )
        with patch("rassa.blueprints.producto_imagen.views.upload_image") as mock_upload:
            mock_upload.side_effect = ValueError("Tipo de archivo no permitido")
            response = self.client.post(
                reverse("producto-imagen-list", args=[self.producto.id_producto]),
                {"archivo": fake_image},
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_db_fail_cleans_drive_file(self):
        """CRÍTICO 2: Si falla el guardado en DB, se limpia el archivo de Drive."""
        fake_image = SimpleUploadedFile(
            "tomate.jpg",
            b"\xff\xd8\xff\xe0" + b"\x00" * 1024,
            content_type="image/jpeg",
        )
        with (
            patch("rassa.blueprints.producto_imagen.views.upload_image") as mock_upload,
            patch("rassa.blueprints.producto_imagen.views.delete_file") as mock_delete,
            patch.object(ProductoImagenSerializer, "save", side_effect=RuntimeError("DB error")),
        ):
            mock_upload.return_value = {
                "url": "https://drive.google.com/uc?id=orphan456&export=download",
                "file_id": "orphan456",
            }
            response = self.client.post(
                reverse("producto-imagen-list", args=[self.producto.id_producto]),
                {"archivo": fake_image},
            )
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        mock_delete.assert_called_once_with("orphan456")
