"""Tests para el blueprint Waste (Mermas)."""

from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from rassa.models import (
    CategoriaProducto,
    DecisionMerma,
    Merma,
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


class WasteBaseTestCase(APITestCase):
    """Setup compartido para tests de mermas."""

    def setUp(self):
        super().setUp()

        # Congelar fecha para determinismo
        patcher = patch("django.utils.timezone.localdate")
        self.mock_date = patcher.start()
        self.mock_date.return_value = date(2026, 7, 20)  # Monday
        self.addCleanup(patcher.stop)

        # Crear usuarios
        self.admin = _create_user_with_role("Admin", "admin_test")
        self.vendedor = _create_user_with_role("Vendedor", "vendedor_test")
        self.agricultor = _create_user_with_role("Agricultor", "agricultor_test")

        # Crear catálogos base
        self.categoria = CategoriaProducto.objects.create(nombre="Frutas", descripcion="Frutas", estado=True)
        self.producto = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            es_perecedero=True,
            estado=True,
        )
        self.unidad = Unidad.objects.create(nombre="Kilogramo", abreviatura="kg", tipo="Kilogramo", estado=True)

        # Crear decisión de merma
        self.decision = DecisionMerma.objects.create(decision="Donar")

        # Crear publicación semanal y producto semanal con stock
        self.publicacion = PublicacionSemanal.objects.create(
            fk_agricultor=self.agricultor.usuario,
            fecha_publicacion=date(2026, 7, 20),
            semana=30,
            estado=PublicacionSemanal.ESTADO_PUBLICADO,
        )
        self.producto_semanal = ProductoSemanal.objects.create(
            fk_publicacion=self.publicacion,
            fk_producto=self.producto,
            fk_unidad=self.unidad,
            stock=50,
            precio="25.00",
            foto="http://example.com/foto.jpg",
            estado=ProductoSemanal.ESTADO_ACTIVO,
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
        if message is not None:
            self.assertEqual(body.get("message"), message)

    def _create_merma_payload(self, **overrides):
        payload = {
            "fk_producto_semanal": self.producto_semanal.id_producto_semanal,
            "cantidad": 5,
            "motivo": "Producto dañado",
            "comentarios": "Se encontró moho",
            "fk_decision": self.decision.id_decision,
        }
        payload.update(overrides)
        return payload


# ======================================================================
# DECISIONES MERMA — CRUD
# ======================================================================


class DecisionMermaTests(WasteBaseTestCase):
    """Tests para el catálogo de decisiones de merma (solo admin)."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)

    def test_admin_list_decisiones(self):
        data = self._assert_success_envelope(self.client.get(reverse("decision-merma-list")))
        self.assertIn("count", data)
        self.assertIn("results", data)
        self.assertGreaterEqual(data["count"], 1)

    def test_admin_create_decision(self):
        data = self._assert_success_envelope(
            self.client.post(reverse("decision-merma-list"), {"decision": "Compostar"}, format="json"),
            status_code=status.HTTP_201_CREATED,
        )
        self.assertEqual(data["decision"], "Compostar")
        self.assertTrue(data["estado"])

    def test_admin_update_decision(self):
        data = self._assert_success_envelope(
            self.client.patch(
                reverse("decision-merma-detail", args=[self.decision.id_decision]),
                {"decision": "Reciclar"},
                format="json",
            )
        )
        self.assertEqual(data["decision"], "Reciclar")

    def test_admin_delete_decision_soft(self):
        self._assert_message_envelope(
            self.client.delete(reverse("decision-merma-detail", args=[self.decision.id_decision])),
        )
        self.decision.refresh_from_db()
        self.assertFalse(self.decision.estado)

    def test_admin_list_incluye_inactivos(self):
        # Crear una decisión y desactivarla directamente
        d = DecisionMerma.objects.create(decision="Compostar", estado=False)
        response = self.client.get(reverse("decision-merma-list"), {"incluir_inactivos": "true"})
        data = self._assert_success_envelope(response)
        ids = [item["id_decision"] for item in data["results"]]
        self.assertIn(d.id_decision, ids)

    def test_non_admin_cannot_manage_decisiones(self):
        """Vendedor/agricultor NO puede crear/editar/borrar decisiones."""
        for user in [self.vendedor, self.agricultor]:
            self.client.force_authenticate(user)
            # Create
            response = self.client.post(reverse("decision-merma-list"), {"decision": "Compostar"}, format="json")
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            # Update
            response = self.client.patch(
                reverse("decision-merma-detail", args=[self.decision.id_decision]),
                {"decision": "Nueva"},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            # Delete
            response = self.client.delete(reverse("decision-merma-detail", args=[self.decision.id_decision]))
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ======================================================================
# MERMA CREATE
# ======================================================================


class MermaCreateTests(WasteBaseTestCase):
    """Tests para creación de mermas con descuento de stock."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.vendedor)

    def test_vendedor_create_merma(self):
        """Vendedor puede registrar merma, stock se descuenta."""
        stock_inicial = self.producto_semanal.stock
        data = self._assert_success_envelope(
            self.client.post(reverse("merma-list"), self._create_merma_payload(), format="json"),
            status_code=status.HTTP_201_CREATED,
            message="Merma registrada",
        )
        self.assertEqual(data["cantidad"], 5)
        self.assertEqual(data["motivo"], "Producto dañado")
        self.assertIn("producto_info", data)
        self.assertIn("decision_info", data)
        self.producto_semanal.refresh_from_db()
        self.assertEqual(self.producto_semanal.stock, stock_inicial - 5)

    def test_admin_create_merma(self):
        """Admin puede registrar merma."""
        self.client.force_authenticate(self.admin)
        stock_inicial = self.producto_semanal.stock
        data = self._assert_success_envelope(
            self.client.post(reverse("merma-list"), self._create_merma_payload(), format="json"),
            status_code=status.HTTP_201_CREATED,
            message="Merma registrada",
        )
        self.assertEqual(data["cantidad"], 5)
        self.producto_semanal.refresh_from_db()
        self.assertEqual(self.producto_semanal.stock, stock_inicial - 5)

    def test_merma_insufficient_stock(self):
        """Error si cantidad > stock disponible."""
        response = self.client.post(
            reverse("merma-list"),
            self._create_merma_payload(cantidad=999),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertIn("fk_producto_semanal", body)

    def test_merma_invalid_producto(self):
        """Error si producto_semanal no existe."""
        response = self.client.post(
            reverse("merma-list"),
            self._create_merma_payload(fk_producto_semanal=99999),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_merma_stock_exacto(self):
        """Si cantidad == stock, queda en 0."""
        data = self._assert_success_envelope(
            self.client.post(
                reverse("merma-list"),
                self._create_merma_payload(cantidad=50),
                format="json",
            ),
            status_code=status.HTTP_201_CREATED,
        )
        self.assertEqual(data["cantidad"], 50)
        self.producto_semanal.refresh_from_db()
        self.assertEqual(self.producto_semanal.stock, 0)

    def test_merma_cantidad_cero_rejected(self):
        """Error si cantidad es 0."""
        response = self.client.post(
            reverse("merma-list"),
            self._create_merma_payload(cantidad=0),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_merma_cantidad_negativa_rejected(self):
        """Error si cantidad es negativa."""
        response = self.client.post(
            reverse("merma-list"),
            self._create_merma_payload(cantidad=-1),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_merma_requiere_motivo(self):
        """Error si motivo está vacío."""
        response = self.client.post(
            reverse("merma-list"),
            self._create_merma_payload(motivo=""),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_agricultor_cannot_create_merma(self):
        """Agricultor NO puede crear merma."""
        self.client.force_authenticate(self.agricultor)
        response = self.client.post(
            reverse("merma-list"),
            self._create_merma_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthorized_cannot_create_merma(self):
        """Usuario no autenticado NO puede crear merma."""
        self.client.force_authenticate(None)
        response = self.client.post(
            reverse("merma-list"),
            self._create_merma_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ======================================================================
# MERMA LIST
# ======================================================================


class MermaListTests(WasteBaseTestCase):
    """Tests para listado de mermas."""

    def setUp(self):
        super().setUp()
        # Crear una merma de prueba directamente
        self.merma = Merma.objects.create(
            fk_producto_semanal=self.producto_semanal,
            cantidad=5,
            motivo="Prueba",
            comentarios="Test",
            fk_decision=self.decision,
        )
        self.client.force_authenticate(self.vendedor)

    def test_vendedor_list_mermas(self):
        data = self._assert_success_envelope(self.client.get(reverse("merma-list")))
        self.assertIn("count", data)
        self.assertIn("results", data)
        self.assertGreaterEqual(data["count"], 1)
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["id_merma"], self.merma.id_merma)

    def test_admin_list_mermas(self):
        self.client.force_authenticate(self.admin)
        data = self._assert_success_envelope(self.client.get(reverse("merma-list")))
        self.assertGreaterEqual(data["count"], 1)

    def test_merma_list_includes_producto_info(self):
        data = self._assert_success_envelope(self.client.get(reverse("merma-list")))
        item = data["results"][0]
        self.assertIn("producto_info", item)
        pi = item["producto_info"]
        self.assertEqual(pi["id"], self.producto_semanal.id_producto_semanal)
        self.assertIn("producto", pi)
        self.assertIn("publicacion", pi)
        self.assertIn("stock_restante", pi)

    def test_merma_list_includes_decision_info(self):
        data = self._assert_success_envelope(self.client.get(reverse("merma-list")))
        item = data["results"][0]
        self.assertIn("decision_info", item)
        di = item["decision_info"]
        self.assertEqual(di["id"], self.decision.id_decision)
        self.assertEqual(di["nombre"], self.decision.decision)

    def test_merma_list_pagination(self):
        data = self._assert_success_envelope(self.client.get(reverse("merma-list")))
        self.assertIn("count", data)
        self.assertIn("results", data)
        self.assertIn("next", data)
        self.assertIn("previous", data)

    def test_agricultor_cannot_list_mermas(self):
        self.client.force_authenticate(self.agricultor)
        response = self.client.get(reverse("merma-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthorized_cannot_list_mermas(self):
        self.client.force_authenticate(None)
        response = self.client.get(reverse("merma-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
