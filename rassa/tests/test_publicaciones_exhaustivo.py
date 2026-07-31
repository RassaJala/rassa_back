"""Tests exhaustivos de seguridad, validación y edge cases para publicaciones."""

from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
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
        # Mockear lunes para que POST /api/publicaciones/ no devuelva 403
        self._patcher = patch("rassa.blueprints.publicacion.views.timezone")
        mock_tz = self._patcher.start()
        mock_tz.localdate.return_value = date(2026, 7, 27)  # lunes

        self.addCleanup(self._patcher.stop)

        self.agricultor = _create_user_with_role("Agricultor", "agri_exh")
        self.cliente = _create_user_with_role("Cliente", "cli_exh")
        self.client.force_authenticate(self.agricultor)

        self.categoria = CategoriaProducto.objects.create(nombre="Frutas", descripcion="Frutas", estado=True)
        self.producto = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            es_perecedero=True,
            estado=True,
        )
        self.unidad = Unidad.objects.create(nombre="Kilogramo", abreviatura="kg", tipo="Kilogramo", estado=True)

    def _create_publicacion(self):
        response = self.client.post(reverse("publicacion-list"))
        return response.json()["data"]

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
# XSS E INYECCIÓN
# ======================================================================


class XSSInjectionTests(PublicacionBaseTestCase):
    """XSS, SQL injection y payloads maliciosos en campos de texto."""

    def test_xss_in_foto_url(self):
        """XSS en foto debe ser rechazado por URLValidator."""
        pub = self._create_publicacion()
        response = self._create_producto_semanal(pub["id_publicacion"], foto="<script>alert(1)</script>")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_xss_in_foto_javascript_url(self):
        """javascript: URI debe ser rechazado."""
        pub = self._create_publicacion()
        response = self._create_producto_semanal(pub["id_publicacion"], foto="javascript:alert(1)")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_xss_in_foto_data_url(self):
        """data: URI debe ser rechazado."""
        pub = self._create_publicacion()
        response = self._create_producto_semanal(pub["id_publicacion"], foto="data:text/html,<script>alert(1)</script>")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_foto_empty_string_allowed(self):
        """Foto vacía debe permitirse en creación (no es requerida hasta publish)."""
        pub = self._create_publicacion()
        response = self._create_producto_semanal(pub["id_publicacion"], foto="")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_foto_null_allowed(self):
        """Foto null debe permitirse en creación."""
        pub = self._create_publicacion()
        response = self._create_producto_semanal(pub["id_publicacion"], foto=None)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_valid_https_foto_accepted(self):
        """URL HTTPS válida debe ser aceptada."""
        pub = self._create_publicacion()
        response = self._create_producto_semanal(pub["id_publicacion"], foto="https://storage.example.com/foto.jpg")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_valid_http_foto_accepted(self):
        """URL HTTP válida debe ser aceptada."""
        pub = self._create_publicacion()
        response = self._create_producto_semanal(pub["id_publicacion"], foto="http://storage.example.com/foto.jpg")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


# ======================================================================
# MASS ASSIGNMENT PROFUNDO
# ======================================================================


class MassAssignmentTests(PublicacionBaseTestCase):
    """Intento de escritura en campos protegidos."""

    def test_cannot_set_fk_agricultor_on_create(self):
        """fk_agricultor es read-only — el POST debe ignorarlo."""
        response = self.client.post(
            reverse("publicacion-list"),
            {"fk_agricultor": 99999},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()["data"]
        self.assertEqual(data["fk_agricultor"], self.agricultor.usuario.pk)

    def test_cannot_set_fk_publicacion_on_create_producto(self):
        """fk_publicacion es read-only — debe tomarse de la URL."""
        pub = self._create_publicacion()
        response = self._create_producto_semanal(pub["id_publicacion"], fk_publicacion=99999)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # El producto se crea en la publicación de la URL, no en 99999
        item = ProductoSemanal.objects.get(pk=response.json()["data"]["id_producto_semanal"])
        self.assertEqual(item.fk_publicacion_id, pub["id_publicacion"])

    def test_cannot_set_creado_en_on_create(self):
        """creado_en es read-only — debe auto-asignarse."""
        pub = self._create_publicacion()
        response = self._create_producto_semanal(pub["id_publicacion"])
        data = response.json()["data"]
        self.assertIsNotNone(data["creado_en"])

    def test_cannot_change_estado_via_patch(self):
        """PATCH con estado=inactivo debe ser ignorado."""
        pub = self._create_publicacion()
        create_resp = self._create_producto_semanal(pub["id_publicacion"])
        item_id = create_resp.json()["data"]["id_producto_semanal"]

        response = self.client.patch(
            reverse("producto-semanal-detail", args=[pub["id_publicacion"], item_id]),
            {"estado": "inactivo"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["data"]["estado"], "activo")

    def test_cannot_set_id_publicacion_on_patch(self):
        """id_publicacion es read-only en PublicacionSerializer."""
        pub = self._create_publicacion()
        # No hay PATCH en publicaciones (se eliminó), así que verificamos que el endpoint no exista
        response = self.client.patch(
            reverse("publicacion-detail", args=[pub["id_publicacion"]]),
            {"semana": 99},
            format="json",
        )
        # El endpoint no existe más (405 Method Not Allowed)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


# ======================================================================
# OWNERSHIP Y AISLAMIENTO
# ======================================================================


class OwnershipTests(PublicacionBaseTestCase):
    """Aislamiento entre agricultores."""

    def setUp(self):
        super().setUp()
        self.pub_data = self._create_publicacion()
        self.pub_id = self.pub_data["id_publicacion"]
        self._create_producto_semanal(self.pub_id)

        # Segundo agricultor
        self.otro_agricultor = _create_user_with_role("Agricultor", "otro_exh")

    def test_otro_agricultor_no_ve_publicacion(self):
        self.client.force_authenticate(self.otro_agricultor)
        response = self.client.get(reverse("publicacion-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["data"]["count"], 0)

    def test_otro_agricultor_no_ve_detalle(self):
        self.client.force_authenticate(self.otro_agricultor)
        response = self.client.get(reverse("publicacion-detail", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_otro_agricultor_no_puede_publicar(self):
        self.client.force_authenticate(self.otro_agricultor)
        response = self.client.post(reverse("publicacion-publish", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_otro_agricultor_no_puede_cerrar(self):
        self.client.force_authenticate(self.otro_agricultor)
        response = self.client.post(reverse("publicacion-close", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_otro_agricultor_no_ve_productos(self):
        self.client.force_authenticate(self.otro_agricultor)
        response = self.client.get(reverse("producto-semanal-list", args=[self.pub_id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_otro_agricultor_no_puede_eliminar_producto(self):
        item = ProductoSemanal.objects.filter(fk_publicacion_id=self.pub_id).first()
        self.client.force_authenticate(self.otro_agricultor)
        response = self.client.delete(reverse("producto-semanal-detail", args=[self.pub_id, item.pk]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_otro_agricultor_no_puede_restaurar(self):
        item = ProductoSemanal.objects.filter(fk_publicacion_id=self.pub_id).first()
        item.estado = "inactivo"
        item.save()
        self.client.force_authenticate(self.otro_agricultor)
        response = self.client.post(reverse("producto-semanal-restore", args=[self.pub_id, item.pk]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ======================================================================
# VALIDACIONES DE PUBLISH
# ======================================================================


class PublishValidationTests(PublicacionBaseTestCase):
    """Validaciones al intentar publicar."""

    def test_publish_fails_when_producto_estado_inactivo(self):
        """Producto inactivo (fk_producto.estado=False) debe permitirse.
        (No hay validación de esto actualmente — documentado como limitación)"""
        pub = self._create_publicacion()
        self._create_producto_semanal(pub["id_publicacion"])
        # Desactivar el producto del catálogo
        self.producto.estado = False
        self.producto.save()
        response = self.client.post(reverse("publicacion-publish", args=[pub["id_publicacion"]]))
        # Actualmente publica igual — es el comportamiento actual
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_publish_fails_when_all_products_inactive(self):
        """Sin productos activos, no se puede publicar."""
        pub = self._create_publicacion()
        create_resp = self._create_producto_semanal(pub["id_publicacion"])
        item_id = create_resp.json()["data"]["id_producto_semanal"]
        # Soft-delete el producto
        self.client.delete(reverse("producto-semanal-detail", args=[pub["id_publicacion"], item_id]))
        response = self.client.post(reverse("publicacion-publish", args=[pub["id_publicacion"]]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("No hay productos activos", response.json()["error"])


# ======================================================================
# RESTORE
# ======================================================================


class RestoreTests(PublicacionBaseTestCase):
    """Restauración de productos eliminados."""

    def test_restore_full_flow(self):
        """Flujo completo: crear → eliminar → restaurar → listar como activo."""
        pub = self._create_publicacion()
        create_resp = self._create_producto_semanal(pub["id_publicacion"])
        item_id = create_resp.json()["data"]["id_producto_semanal"]

        # Eliminar (soft-delete)
        self.client.delete(reverse("producto-semanal-detail", args=[pub["id_publicacion"], item_id]))

        # Verificar inactivo
        item = ProductoSemanal.objects.get(pk=item_id)
        self.assertEqual(item.estado, "inactivo")

        # No aparece en list
        list_resp = self.client.get(reverse("producto-semanal-list", args=[pub["id_publicacion"]]))
        self.assertEqual(list_resp.json()["data"]["count"], 0)

        # Restaurar
        restore_resp = self.client.post(reverse("producto-semanal-restore", args=[pub["id_publicacion"], item_id]))
        self.assertEqual(restore_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(restore_resp.json()["data"]["estado"], "activo")

        # Aparece en list de nuevo
        list_resp = self.client.get(reverse("producto-semanal-list", args=[pub["id_publicacion"]]))
        self.assertEqual(list_resp.json()["data"]["count"], 1)

    def test_restore_producto_in_published_returns_404(self):
        """No se puede restaurar un producto en publicación publicada (no existe como inactivo)."""
        pub = self._create_publicacion()
        create_resp = self._create_producto_semanal(pub["id_publicacion"])
        item_id = create_resp.json()["data"]["id_producto_semanal"]

        # Publicar
        self.client.post(reverse("publicacion-publish", args=[pub["id_publicacion"]]))

        # Intentar restaurar un producto activo
        response = self.client.post(reverse("producto-semanal-restore", args=[pub["id_publicacion"], item_id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ======================================================================
# FILTROS Y PAGINACIÓN
# ======================================================================


class FilterPaginationTests(PublicacionBaseTestCase):
    """Filtros y estructura de paginación."""

    def test_filter_by_estado_published(self):
        """Filtrar publicaciones por estado publicado."""
        pub = self._create_publicacion()
        self._create_producto_semanal(pub["id_publicacion"])
        self.client.post(reverse("publicacion-publish", args=[pub["id_publicacion"]]))

        response = self.client.get(reverse("publicacion-list"), {"estado": "publicado"})
        data = response.json()["data"]
        for item in data["results"]:
            self.assertEqual(item["estado"], "publicado")

    def test_filter_by_estado_draft(self):
        """Filtrar publicaciones por estado borrador."""
        self._create_publicacion()

        response = self.client.get(reverse("publicacion-list"), {"estado": "borrador"})
        data = response.json()["data"]
        for item in data["results"]:
            self.assertEqual(item["estado"], "borrador")

    def test_pagination_structure(self):
        """Verificar estructura de paginación completa."""
        # Override setUp's return_value with side_effect for different weeks
        self._patcher.stop()
        self._patcher = patch("rassa.blueprints.publicacion.views.timezone")
        mock_tz = self._patcher.start()
        self.addCleanup(self._patcher.stop)
        mock_tz.localdate.side_effect = [
            date(2026, 7, 27),
            date(2026, 7, 27),  # pub semana 31
            date(2026, 8, 3),
            date(2026, 8, 3),  # pub semana 32
            date(2026, 8, 10),
            date(2026, 8, 10),  # pub semana 33
        ]
        for _ in range(3):
            self._create_publicacion()

        response = self.client.get(reverse("publicacion-list"))
        data = response.json()["data"]
        self.assertIn("count", data)
        self.assertIn("next", data)
        self.assertIn("previous", data)
        self.assertIn("results", data)
        self.assertIsInstance(data["results"], list)

    def test_producto_list_paginated(self):
        """Verificar que productos también usan paginación."""
        pub = self._create_publicacion()
        for _ in range(3):
            self._create_producto_semanal(pub["id_publicacion"])

        response = self.client.get(reverse("producto-semanal-list", args=[pub["id_publicacion"]]))
        data = response.json()["data"]
        self.assertIn("count", data)
        self.assertIn("results", data)
        self.assertEqual(data["count"], 3)


# ======================================================================
# STATE MACHINE — TRANSICIONES COMPLETAS
# ======================================================================


class StateMachineTests(PublicacionBaseTestCase):
    """State machine completa: borrador → publicado → cerrado."""

    def test_full_lifecycle(self):
        """Ciclo de vida completo de una publicación."""
        # 1. Crear borrador
        pub = self._create_publicacion()
        self.assertEqual(pub["estado"], "borrador")

        # 2. Agregar producto
        self._create_producto_semanal(pub["id_publicacion"])

        # 3. Publicar
        pub_resp = self.client.post(reverse("publicacion-publish", args=[pub["id_publicacion"]]))
        self.assertEqual(pub_resp.json()["data"]["estado"], "publicado")

        # 4. Cerrar
        close_resp = self.client.post(reverse("publicacion-close", args=[pub["id_publicacion"]]))
        self.assertEqual(close_resp.json()["data"]["estado"], "cerrado")

    def test_cannot_publish_from_published(self):
        """No se puede publicar una publicación ya publicada."""
        pub = self._create_publicacion()
        self._create_producto_semanal(pub["id_publicacion"])
        self.client.post(reverse("publicacion-publish", args=[pub["id_publicacion"]]))
        response = self.client.post(reverse("publicacion-publish", args=[pub["id_publicacion"]]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_publish_from_closed(self):
        """No se puede publicar una publicación cerrada."""
        pub = self._create_publicacion()
        self._create_producto_semanal(pub["id_publicacion"])
        self.client.post(reverse("publicacion-publish", args=[pub["id_publicacion"]]))
        self.client.post(reverse("publicacion-close", args=[pub["id_publicacion"]]))
        response = self.client.post(reverse("publicacion-publish", args=[pub["id_publicacion"]]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_close_from_draft(self):
        """No se puede cerrar una publicación en borrador."""
        pub = self._create_publicacion()
        response = self.client.post(reverse("publicacion-close", args=[pub["id_publicacion"]]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_close_from_closed(self):
        """No se puede cerrar una publicación ya cerrada."""
        pub = self._create_publicacion()
        self._create_producto_semanal(pub["id_publicacion"])
        self.client.post(reverse("publicacion-publish", args=[pub["id_publicacion"]]))
        self.client.post(reverse("publicacion-close", args=[pub["id_publicacion"]]))
        response = self.client.post(reverse("publicacion-close", args=[pub["id_publicacion"]]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_delete_published(self):
        """No se puede eliminar (cancelar) una publicación publicada."""
        pub = self._create_publicacion()
        self._create_producto_semanal(pub["id_publicacion"])
        self.client.post(reverse("publicacion-publish", args=[pub["id_publicacion"]]))
        response = self.client.delete(reverse("publicacion-detail", args=[pub["id_publicacion"]]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_delete_closed(self):
        """No se puede eliminar (cancelar) una publicación cerrada."""
        pub = self._create_publicacion()
        self._create_producto_semanal(pub["id_publicacion"])
        self.client.post(reverse("publicacion-publish", args=[pub["id_publicacion"]]))
        self.client.post(reverse("publicacion-close", args=[pub["id_publicacion"]]))
        response = self.client.delete(reverse("publicacion-detail", args=[pub["id_publicacion"]]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_draft_sets_cancelado(self):
        """Cancelar una publicación en borrador debe marcarla como cancelado."""
        pub = self._create_publicacion()
        pub_id = pub["id_publicacion"]
        self.client.delete(reverse("publicacion-detail", args=[pub_id]))
        pub_obj = PublicacionSemanal.objects.get(pk=pub_id)
        self.assertEqual(pub_obj.estado, "cancelado")

    def test_cannot_add_product_to_published(self):
        """No se puede agregar producto a publicación publicada."""
        pub = self._create_publicacion()
        self._create_producto_semanal(pub["id_publicacion"])
        self.client.post(reverse("publicacion-publish", args=[pub["id_publicacion"]]))
        response = self._create_producto_semanal(pub["id_publicacion"])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_add_product_to_closed(self):
        """No se puede agregar producto a publicación cerrada."""
        pub = self._create_publicacion()
        self._create_producto_semanal(pub["id_publicacion"])
        self.client.post(reverse("publicacion-publish", args=[pub["id_publicacion"]]))
        self.client.post(reverse("publicacion-close", args=[pub["id_publicacion"]]))
        response = self._create_producto_semanal(pub["id_publicacion"])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_modify_product_in_published(self):
        """No se puede modificar producto en publicación publicada."""
        pub = self._create_publicacion()
        resp = self._create_producto_semanal(pub["id_publicacion"])
        item_id = resp.json()["data"]["id_producto_semanal"]
        self.client.post(reverse("publicacion-publish", args=[pub["id_publicacion"]]))
        response = self.client.patch(
            reverse("producto-semanal-detail", args=[pub["id_publicacion"], item_id]),
            {"stock": 99},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_delete_product_in_published(self):
        """No se puede eliminar producto en publicación publicada."""
        pub = self._create_publicacion()
        resp = self._create_producto_semanal(pub["id_publicacion"])
        item_id = resp.json()["data"]["id_producto_semanal"]
        self.client.post(reverse("publicacion-publish", args=[pub["id_publicacion"]]))
        response = self.client.delete(reverse("producto-semanal-detail", args=[pub["id_publicacion"], item_id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ======================================================================
# UNIQUENESS
# ======================================================================


class UniquenessTests(PublicacionBaseTestCase):
    """Restricciones de unicidad."""

    def test_unique_agricultor_semana_raises_error(self):
        """Dos publicaciones misma semana+mismo agricultor deben fallar."""
        pub = self._create_publicacion()
        with self.assertRaises(IntegrityError):
            PublicacionSemanal.objects.create(
                fk_agricultor=self.agricultor.usuario,
                fecha_publicacion=pub["fecha_publicacion"],
                semana=pub["semana"],
                estado="borrador",
            )

    def test_otro_agricultor_misma_semana_ok(self):
        """Dos agricultores diferentes pueden tener la misma semana."""
        otro = _create_user_with_role("Agricultor", "otro_unique")
        pub = self._create_publicacion()
        PublicacionSemanal.objects.create(
            fk_agricultor=otro.usuario,
            fecha_publicacion=pub["fecha_publicacion"],
            semana=pub["semana"],
            estado="borrador",
        )
        # Si no lanza excepción, OK

    def test_mismo_agricultor_distinta_semana_ok(self):
        """Mismo agricultor puede tener publicaciones en distintas semanas."""
        pub = self._create_publicacion()
        PublicacionSemanal.objects.create(
            fk_agricultor=self.agricultor.usuario,
            fecha_publicacion="2026-12-28",
            semana=pub["semana"] + 3,
            estado="borrador",
        )
        # Si no lanza excepción, OK


# ======================================================================
# PRODUCTO CATÁLOGO INACTIVO (PROTECT)
# ======================================================================


class ProductoDeleteProtectionTests(PublicacionBaseTestCase):
    """Verificar PROTECT en FK producto."""

    def test_cannot_delete_producto_with_referencias(self):
        """No se puede eliminar un Producto referenciado por ProductoSemanal."""
        pub = self._create_publicacion()
        self._create_producto_semanal(pub["id_publicacion"])
        with self.assertRaises(IntegrityError):  # ProtectedError subclass
            self.producto.delete()

    def test_can_deactivate_producto(self):
        """Se puede desactivar un Producto sin eliminar."""
        self.producto.estado = False
        self.producto.save()
        self.producto.refresh_from_db()
        self.assertFalse(self.producto.estado)
