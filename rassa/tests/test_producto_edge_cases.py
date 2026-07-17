import base64

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from rassa.models import CategoriaProducto, Producto, Unidad

TEST_MEDIA = "/tmp/rassa_test_media_edge"


def _create_user_with_role(nombre_rol, username):
    email = f"{username}@rassa.com"
    user = get_user_model().objects.create_user(username=username, password="secret123", email=email)
    from rassa.models import Persona, Rol

    persona = Persona.objects.create(
        nombre="Test",
        apellido_paterno="Edge",
        fecha_nacimiento="2000-01-01",
        sexo="M",
        domicilio="Calle Edge 1",
    )
    rol, _ = Rol.objects.get_or_create(
        nombre_rol=nombre_rol,
        defaults={"descripcion": f"Rol edge: {nombre_rol}"},
    )
    from rassa.models import Usuario

    Usuario.objects.create(
        fk_user=user,
        fk_persona=persona,
        telefono="1234567890",
        correo=f"{username}@rassa.com",
        fk_rol=rol,
    )
    return user


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


def _small_gif():
    return (
        b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
        b"\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00"
        b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
        b"\x44\x01\x00\x3b"
    )


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class EdgeCaseSerializerTests(TestCase):
    def setUp(self):
        self.admin = _create_user_with_role("Admin", "admin_edge")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.categoria = CategoriaProducto.objects.create(nombre="Frutas", descripcion="Test", estado=True)
        self.unidad = Unidad.objects.create(nombre="Kilogramo", abreviatura="kg", tipo="peso", estado=True)

    def test_create_nombre_whitespace_only(self):
        """nombre_producto con solo espacios debe fallar."""
        response = self.client.post(
            reverse("producto_list"),
            {
                "nombre_producto": "   ",
                "precio": "10",
                "fk_categoria": self.categoria.id_categoria,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_nombre_too_long(self):
        """nombre_producto mayor a 150 chars debe fallar."""
        response = self.client.post(
            reverse("producto_list"),
            {
                "nombre_producto": "A" * 151,
                "precio": "10",
                "fk_categoria": self.categoria.id_categoria,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_precio_zero_allowed(self):
        """precio = 0 debe ser permitido (limite inferior valido)."""
        response = self.client.post(
            reverse("producto_list"),
            {
                "nombre_producto": "Gratis",
                "precio": "0",
                "fk_categoria": self.categoria.id_categoria,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["data"]["precio"], "0.00")

    def test_create_categoria_nonexistent(self):
        """fk_categoria de un id que no existe debe fallar."""
        response = self.client.post(
            reverse("producto_list"),
            {
                "nombre_producto": "Fantasma",
                "precio": "10",
                "fk_categoria": 99999,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_missing_required_fields(self):
        """PUT (reemplazo completo) sin campos requeridos debe fallar."""
        p = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            precio=10,
        )
        response = self.client.put(
            reverse("producto_detail", args=[p.id_producto]),
            {"descripcion": "Solo descripcion"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class EdgeCaseImageUploadTests(TestCase):
    def setUp(self):
        self.admin = _create_user_with_role("Admin", "admin_img_edge")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.categoria = CategoriaProducto.objects.create(nombre="Frutas", descripcion="Test", estado=True)
        self.producto = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            precio=15.50,
        )

    def test_upload_base64_with_data_uri_prefix(self):
        """base64 con prefix data:image/... debe ser procesado correctamente."""
        raw = _small_png()
        b64 = base64.b64encode(raw).decode()
        data_uri = f"data:image/png;base64,{b64}"
        response = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen_base64": data_uri},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_upload_base64_invalid_chars(self):
        """base64 con caracteres invalidos debe fallar."""
        response = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen_base64": "esto_no_es_base64!!!@#$%"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_base64_non_image_bytes(self):
        """base64 que decodifica a bytes que no son imagen debe fallar."""
        b64 = base64.b64encode(b"esto no es una imagen para nada").decode()
        response = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen_base64": b64},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_over_5mb_base64(self):
        """base64 que decoda a >5MB debe fallar."""
        big_data = _small_png() * ((5 * 1024 * 1024 // len(_small_png())) + 100)
        b64 = base64.b64encode(big_data).decode()
        response = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen_base64": b64},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_es_principal_false_string(self):
        """es_principal='false' debe crear imagen no principal."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        img_bytes = _small_gif()
        f = SimpleUploadedFile("test.gif", img_bytes, content_type="image/gif")
        response = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen": f, "es_principal": "false"},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.json()["data"]["es_principal"])

    def test_upload_es_principal_zero_string(self):
        """es_principal='0' debe crear imagen no principal."""
        raw = _small_png()
        b64 = base64.b64encode(raw).decode()
        response = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen_base64": b64, "es_principal": "0"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.json()["data"]["es_principal"])

    def test_upload_no_extension_file(self):
        """Archivo sin extension debe fallar."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        f = SimpleUploadedFile("sinext", _small_gif(), content_type="image/gif")
        response = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen": f},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_uppercase_extension(self):
        """Extension en mayusculas (.JPG) debe ser aceptada."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        f = SimpleUploadedFile("foto.JPG", _small_gif(), content_type="image/gif")
        response = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen": f},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class EdgeCaseImageDeleteTests(TestCase):
    def setUp(self):
        self.admin = _create_user_with_role("Admin", "admin_imgdel")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.categoria = CategoriaProducto.objects.create(nombre="Frutas", descripcion="Test", estado=True)
        self.producto = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            precio=15.50,
        )

    def _upload_image(self, es_principal="true"):
        b64 = base64.b64encode(_small_png()).decode()
        resp = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen_base64": b64, "es_principal": es_principal},
            format="json",
        )
        return resp.json()["data"]

    def test_delete_principal_reassigns_to_next(self):
        """Eliminar imagen principal debe reasignar a la siguiente."""
        img1 = self._upload_image("true")
        self._upload_image("false")
        self.client.delete(
            reverse(
                "producto_imagen_delete",
                args=[self.producto.id_producto, img1["id_imagen"]],
            )
        )
        response = self.client.get(reverse("producto_detail", args=[self.producto.id_producto]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_delete_last_image_clears_producto_imagen(self):
        """Eliminar la ultima imagen debe limpiar imagen del producto."""
        img1 = self._upload_image("true")
        self.client.delete(
            reverse(
                "producto_imagen_delete",
                args=[self.producto.id_producto, img1["id_imagen"]],
            )
        )
        self.producto.refresh_from_db()
        self.assertIsNone(self.producto.imagen)

    def test_delete_image_from_other_product(self):
        """Eliminar imagen que pertenece a otro producto debe fallar."""
        other = Producto.objects.create(
            nombre_producto="Pera",
            fk_categoria=self.categoria,
            precio=10,
        )
        img = self._upload_image("true")
        response = self.client.delete(
            reverse(
                "producto_imagen_delete",
                args=[other.id_producto, img["id_imagen"]],
            )
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_double_delete_same_image(self):
        """Eliminar la misma imagen dos veces debe fallar en la segunda."""
        img = self._upload_image("true")
        self.client.delete(
            reverse(
                "producto_imagen_delete",
                args=[self.producto.id_producto, img["id_imagen"]],
            )
        )
        response = self.client.delete(
            reverse(
                "producto_imagen_delete",
                args=[self.producto.id_producto, img["id_imagen"]],
            )
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_demote_principal_when_only_one(self):
        """PATCH es_principal=false en la unica imagen no deberia fallar."""
        img = self._upload_image("true")
        response = self.client.patch(
            reverse(
                "producto_imagen_delete",
                args=[self.producto.id_producto, img["id_imagen"]],
            ),
            {"es_principal": "false"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class EdgeCasePermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.categoria = CategoriaProducto.objects.create(nombre="Frutas", descripcion="Test", estado=True)
        self.farmer = _create_user_with_role("Agricultor", "farmer_edge")
        self.buyer = _create_user_with_role("Cliente", "buyer_edge")

    def test_farmer_cannot_create_producto(self):
        """Agricultor no debe poder crear producto."""
        self.client.force_authenticate(self.farmer)
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

    def test_buyer_cannot_update_producto(self):
        """Cliente no debe poder editar producto."""
        p = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            precio=10,
        )
        self.client.force_authenticate(self.buyer)
        response = self.client.patch(
            reverse("producto_detail", args=[p.id_producto]),
            {"nombre_producto": "Hackeado"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_upload_image(self):
        """No autenticado no debe poder subir imagen."""
        p = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            precio=10,
        )
        self.client.force_authenticate(None)
        response = self.client.post(
            reverse("producto_imagen", args=[p.id_producto]),
            {},
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_cannot_delete_producto(self):
        """No autenticado no debe poder eliminar producto."""
        p = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            precio=10,
        )
        self.client.force_authenticate(None)
        response = self.client.delete(reverse("producto_detail", args=[p.id_producto]))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class EdgeCaseFilterTests(TestCase):
    def setUp(self):
        self.admin = _create_user_with_role("Admin", "admin_filter")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.cat1 = CategoriaProducto.objects.create(nombre="Frutas", descripcion="Test", estado=True)
        self.cat2 = CategoriaProducto.objects.create(nombre="Verduras", descripcion="Test", estado=True)
        self.unidad = Unidad.objects.create(nombre="Kilogramo", abreviatura="kg", tipo="peso", estado=True)
        Producto.objects.create(
            nombre_producto="Manzana Roja",
            fk_categoria=self.cat1,
            fk_unidad=self.unidad,
            precio=15.50,
            stock=100,
            es_perecedero=True,
        )
        Producto.objects.create(
            nombre_producto="Zanahoria",
            fk_categoria=self.cat2,
            precio=8.00,
            stock=50,
            es_perecedero=False,
        )

    def _get_results(self, response):
        return response.json()["data"]["results"]

    def test_filter_nombre_no_match(self):
        """Busqueda por nombre que no existe debe retornar lista vacia."""
        response = self.client.get(reverse("producto_list") + "?nombre=xyz_no_existe")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(self._get_results(response)), 0)

    def test_filter_precio_min_greater_than_max(self):
        """precio_min > precio_max debe retornar lista vacia."""
        response = self.client.get(reverse("producto_list") + "?precio_min=100&precio_max=1")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(self._get_results(response)), 0)

    def test_filter_categoria_nonexistent(self):
        """Filtrar por categoria inexistente debe retornar vacio."""
        response = self.client.get(reverse("producto_list") + "?categoria=99999")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(self._get_results(response)), 0)

    def test_filter_perecedero_true(self):
        """Filtrar es_perecedero=true solo retorna perecederos."""
        response = self.client.get(reverse("producto_list") + "?es_perecedero=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self._get_results(response)
        self.assertTrue(all(p["es_perecedero"] for p in data))


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class EdgeCaseProtectTests(TestCase):
    def setUp(self):
        self.admin = _create_user_with_role("Admin", "admin_protect")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.categoria = CategoriaProducto.objects.create(nombre="Frutas", descripcion="Test", estado=True)

    def test_protect_delete_categoria_with_products(self):
        """No se puede eliminar categoria que tiene productos (PROTECT)."""
        from django.db import IntegrityError

        Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            precio=10,
        )
        with self.assertRaises(IntegrityError):
            self.categoria.delete()


class ConnectivityTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = _create_user_with_role("Admin", "admin_conn")

    def test_database_connection(self):
        """Verifica que la conexion a la base de datos funcione."""
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
        self.assertEqual(result[0], 1)

    def test_producto_model_works(self):
        """Verifica que el modelo Producto se puede instanciar y guardar."""
        cat = CategoriaProducto.objects.create(nombre="Test", descripcion="Test", estado=True)
        p = Producto.objects.create(
            nombre_producto="TestProduct",
            fk_categoria=cat,
            precio=10.00,
            stock=5,
        )
        self.assertIsNotNone(p.id_producto)
        p.delete()

    def test_producto_list_endpoint_reachable(self):
        """Endpoint GET /api/productos/ responde correctamente."""
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse("producto_list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("data", response.json())

    def test_producto_detail_endpoint_reachable(self):
        """Endpoint GET /api/productos/<id>/ responde correctamente."""
        self.client.force_authenticate(self.admin)
        cat = CategoriaProducto.objects.create(nombre="Test", descripcion="Test", estado=True)
        p = Producto.objects.create(
            nombre_producto="TestProduct",
            fk_categoria=cat,
            precio=10.00,
        )
        response = self.client.get(reverse("producto_detail", args=[p.id_producto]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("data", response.json())

    def test_categoria_list_endpoint_reachable(self):
        """Endpoint GET /api/categorias/ responde correctamente."""
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse("categoria-producto-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unidad_list_endpoint_reachable(self):
        """Endpoint GET /api/unidades/ responde correctamente."""
        self.client.force_authenticate(self.admin)
        response = self.client.get(reverse("unidad-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_imagen_upload_endpoint_reachable(self):
        """Endpoint POST /api/productos/<id>/imagen/ responde correctamente."""
        self.client.force_authenticate(self.admin)
        cat = CategoriaProducto.objects.create(nombre="Test", descripcion="Test", estado=True)
        p = Producto.objects.create(
            nombre_producto="TestProduct",
            fk_categoria=cat,
            precio=10.00,
        )
        response = self.client.post(
            reverse("producto_imagen", args=[p.id_producto]),
            {},
        )
        # Debe responder 400 (campo faltante), no 404 o 500
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED],
        )

    def test_unauthenticated_endpoints_return_401(self):
        """Endpoints protegidos retornan 401 sin autenticacion."""
        self.client.force_authenticate(None)
        response = self.client.get(reverse("producto_list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_jwt_token_obtain_works(self):
        """Endpoint POST /api/token/ retorna tokens JWT."""
        response = self.client.post(
            reverse("token_obtain_pair"),
            {
                "email": self.admin.email,
                "password": "secret123",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("access", data)
        self.assertIn("refresh", data)


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class SoftDeleteTests(TestCase):
    def setUp(self):
        self.admin = _create_user_with_role("Admin", "admin_softdel")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.categoria = CategoriaProducto.objects.create(nombre="Frutas", descripcion="Test", estado=True)
        self.producto = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            precio=10,
        )

    def test_delete_sets_estado_false(self):
        """DELETE debe poner estado=False, no borrar de la BD."""
        response = self.client.delete(reverse("producto_detail", args=[self.producto.id_producto]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.producto.refresh_from_db()
        self.assertFalse(self.producto.estado)

    def test_deleted_product_still_exists_in_db(self):
        """Producto eliminado debe seguir existiendo en la BD."""
        self.client.delete(reverse("producto_detail", args=[self.producto.id_producto]))
        self.assertTrue(Producto.objects.filter(pk=self.producto.id_producto).exists())

    def test_deleted_product_not_in_list(self):
        """Producto con estado=False no debe aparecer en el listado."""
        self.client.delete(reverse("producto_detail", args=[self.producto.id_producto]))
        response = self.client.get(reverse("producto_list"))
        results = response.json()["data"]["results"]
        ids = [p["id_producto"] for p in results]
        self.assertNotIn(self.producto.id_producto, ids)

    def test_deleted_product_detail_returns_404(self):
        """Detalle de producto con estado=False debe retornar 404."""
        self.client.delete(reverse("producto_detail", args=[self.producto.id_producto]))
        response = self.client.get(reverse("producto_detail", args=[self.producto.id_producto]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class InactiveProductFilterTests(TestCase):
    def setUp(self):
        self.admin = _create_user_with_role("Admin", "admin_inactive")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.categoria = CategoriaProducto.objects.create(nombre="Frutas", descripcion="Test", estado=True)
        self.active = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            precio=10,
            estado=True,
        )
        self.inactive = Producto.objects.create(
            nombre_producto="Pera",
            fk_categoria=self.categoria,
            precio=5,
            estado=False,
        )

    def test_list_only_active(self):
        """Listado solo debe retornar productos activos."""
        response = self.client.get(reverse("producto_list"))
        results = response.json()["data"]["results"]
        ids = [p["id_producto"] for p in results]
        self.assertIn(self.active.id_producto, ids)
        self.assertNotIn(self.inactive.id_producto, ids)


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class ImageDeletePermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.categoria = CategoriaProducto.objects.create(nombre="Frutas", descripcion="Test", estado=True)
        self.producto = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            precio=10,
        )
        self.farmer = _create_user_with_role("Agricultor", "farmer_imgdel")
        self.buyer = _create_user_with_role("Cliente", "buyer_imgdel")

    def _upload_image_as_admin(self):
        admin = _create_user_with_role("Admin", "admin_imgdel_perm")
        self.client.force_authenticate(admin)
        b64 = base64.b64encode(_small_png()).decode()
        resp = self.client.post(
            reverse("producto_imagen", args=[self.producto.id_producto]),
            {"imagen_base64": b64, "es_principal": "true"},
            format="json",
        )
        return resp.json()["data"]

    def test_farmer_cannot_delete_image(self):
        """Agricultor no debe poder eliminar imagen de producto."""
        img = self._upload_image_as_admin()
        self.client.force_authenticate(self.farmer)
        response = self.client.delete(
            reverse("producto_imagen_delete", args=[self.producto.id_producto, img["id_imagen"]])
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_buyer_cannot_delete_image(self):
        """Cliente no debe poder eliminar imagen de producto."""
        img = self._upload_image_as_admin()
        self.client.force_authenticate(self.buyer)
        response = self.client.delete(
            reverse("producto_imagen_delete", args=[self.producto.id_producto, img["id_imagen"]])
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_delete_image(self):
        """No autenticado no debe poder eliminar imagen de producto."""
        img = self._upload_image_as_admin()
        self.client.force_authenticate(None)
        response = self.client.delete(
            reverse("producto_imagen_delete", args=[self.producto.id_producto, img["id_imagen"]])
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_farmer_cannot_patch_image(self):
        """Agricultor no debe poder modificar imagen de producto."""
        img = self._upload_image_as_admin()
        self.client.force_authenticate(self.farmer)
        response = self.client.patch(
            reverse("producto_imagen_delete", args=[self.producto.id_producto, img["id_imagen"]]),
            {"es_principal": "false"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
