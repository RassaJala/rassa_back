from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class CatalogCrudTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tester", password="secret123")
        self.client.force_authenticate(self.user)

    def test_categories_crud(self):
        create_response = self.client.post(
            reverse("categoria-producto-list"),
            {"nombre": "Frutas", "descripcion": "Productos frutales", "estado": True},
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        category_id = create_response.json()["data"]["id_categoria"]
        list_response = self.client.get(reverse("categoria-producto-list"))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(list_response.json()["data"]), 1)

        detail_response = self.client.get(reverse("categoria-producto-detail", args=[category_id]))
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)

        patch_response = self.client.patch(
            reverse("categoria-producto-detail", args=[category_id]),
            {"nombre": "Frutas y Verduras"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)

        delete_response = self.client.delete(reverse("categoria-producto-detail", args=[category_id]))
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

    def test_units_crud(self):
        create_response = self.client.post(
            reverse("unidad-list"),
            {"nombre": "Kilogramo", "abreviatura": "kg", "estado": True},
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        unit_id = create_response.json()["data"]["id_unidad"]
        list_response = self.client.get(reverse("unidad-list"))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(list_response.json()["data"]), 1)

        detail_response = self.client.get(reverse("unidad-detail", args=[unit_id]))
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)

        patch_response = self.client.patch(
            reverse("unidad-detail", args=[unit_id]),
            {"abreviatura": "kgm"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)

        delete_response = self.client.delete(reverse("unidad-detail", args=[unit_id]))
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
