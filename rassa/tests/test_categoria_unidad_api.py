from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from rassa.models import CategoriaProducto, Unidad


class CategoriaUnidadAPITest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="admin@rassa.com",
            email="admin@rassa.com",
            password="admin123",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_categorias(self):
        CategoriaProducto.objects.create(
            nombre="Verduras",
            descripcion="Verduras frescas",
            estado=True,
        )
        CategoriaProducto.objects.create(
            nombre="Frutas",
            descripcion="Frutas de estación",
            estado=True,
        )

        response = self.client.get("/api/categorias/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertEqual(response.data["results"][0]["nombre"], "Verduras")

    def test_create_categoria(self):
        payload = {
            "nombre": "Semillas",
            "descripcion": "Semillas orgánicas",
            "estado": True,
        }
        response = self.client.post("/api/categorias/", payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["nombre"], payload["nombre"])
        self.assertEqual(response.data["descripcion"], payload["descripcion"])
        self.assertTrue(response.data["estado"])

    def test_patch_categoria(self):
        categoria = CategoriaProducto.objects.create(
            nombre="Legumbres",
            descripcion="Alimentos secos",
            estado=True,
        )

        response = self.client.patch(
            f"/api/categorias/{categoria.id_categoria}/",
            {"descripcion": "Legumbres y granos"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["descripcion"], "Legumbres y granos")

    def test_delete_categoria_soft_deletes(self):
        categoria = CategoriaProducto.objects.create(
            nombre="Hierbas",
            descripcion="Hierbas aromáticas",
            estado=True,
        )

        response = self.client.delete(f"/api/categorias/{categoria.id_categoria}/")

        self.assertEqual(response.status_code, 204)
        categoria.refresh_from_db()
        self.assertFalse(categoria.estado)

        list_response = self.client.get("/api/categorias/")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data["results"]), 0)

    def test_list_unidades_includes_abreviatura(self):
        Unidad.objects.create(
            tipo="Kilogramo",
            abreviatura="kg",
            estado=True,
        )
        Unidad.objects.create(
            tipo="Litro",
            abreviatura="lt",
            estado=True,
        )

        response = self.client.get("/api/unidades/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertEqual(response.data["results"][0]["abreviatura"], "kg")

    def test_create_unidad(self):
        payload = {
            "tipo": "Caja",
            "abreviatura": "cja",
            "estado": True,
        }
        response = self.client.post("/api/unidades/", payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["tipo"], payload["tipo"])
        self.assertEqual(response.data["abreviatura"], payload["abreviatura"])

    def test_delete_unidad_soft_deletes(self):
        unidad = Unidad.objects.create(
            tipo="Pieza",
            abreviatura="pz",
            estado=True,
        )

        response = self.client.delete(f"/api/unidades/{unidad.id_unidad}/")

        self.assertEqual(response.status_code, 204)
        unidad.refresh_from_db()
        self.assertFalse(unidad.estado)

        list_response = self.client.get("/api/unidades/")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.data["results"]), 0)
