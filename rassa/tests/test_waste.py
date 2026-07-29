"""Tests para el blueprint Waste (Mermas)."""

from datetime import date
from threading import Barrier, Thread
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

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
from rassa.views import CatalogPagination


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

    def test_admin_retrieve_decision(self):
        data = self._assert_success_envelope(
            self.client.get(reverse("decision-merma-detail", args=[self.decision.id_decision]))
        )
        self.assertEqual(data["id_decision"], self.decision.id_decision)
        self.assertEqual(data["decision"], self.decision.decision)
        self.assertTrue(data["estado"])

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
        response = self.client.patch(
            reverse("decision-merma-detail", args=[self.decision.id_decision]),
            {"decision": "Reciclar"},
            format="json",
        )
        body = response.json()
        self.assertEqual(body.get("message"), "Decisión actualizada correctamente.")
        data = self._assert_success_envelope(response)
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
        # Restore admin auth so subsequent tests are not polluted
        self.client.force_authenticate(self.admin)


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
        """Error 404 si producto_semanal no existe."""
        response = self.client.post(
            reverse("merma-list"),
            self._create_merma_payload(fk_producto_semanal=99999),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        body = response.json()
        self.assertIn("fk_producto_semanal", body)

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

    def test_merma_sin_comentarios_guarda_null(self):
        """Si no se envía comentarios, se guarda como NULL, no como ''."""
        payload = self._create_merma_payload()
        del payload["comentarios"]
        data = self._assert_success_envelope(
            self.client.post(reverse("merma-list"), payload, format="json"),
            status_code=status.HTTP_201_CREATED,
        )
        self.assertIsNone(data["comentarios"])

    def test_merma_con_comentarios_null_guarda_null(self):
        """Si se envía comentarios como null, se guarda como NULL."""
        data = self._assert_success_envelope(
            self.client.post(
                reverse("merma-list"),
                self._create_merma_payload(comentarios=None),
                format="json",
            ),
            status_code=status.HTTP_201_CREATED,
        )
        self.assertIsNone(data["comentarios"])

    def test_merma_decision_inactiva_rechazada(self):
        """Error si fk_decision está desactivada."""
        decision_inactiva = DecisionMerma.objects.create(decision="Tirar", estado=False)
        response = self.client.post(
            reverse("merma-list"),
            self._create_merma_payload(fk_decision=decision_inactiva.id_decision),
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

    def test_merma_list_incluye_inactivos(self):
        """incluir_inactivos=true muestra mermas inactivas."""
        m = Merma.objects.create(
            cantidad=1,
            motivo="Test inactivo",
            fk_decision=self.decision,
            fk_producto_semanal=self.producto_semanal,
            estado=False,
        )
        data = self._assert_success_envelope(self.client.get(reverse("merma-list"), {"incluir_inactivos": "true"}))
        ids = [item["id_merma"] for item in data["results"]]
        self.assertIn(m.id_merma, ids)

    def test_merma_list_pagination(self):
        """Paginación: 25 mermas → page 1 tiene page_size, next apunta a page 2."""
        page_size = CatalogPagination.page_size
        Merma.objects.bulk_create(
            [
                Merma(
                    cantidad=1,
                    motivo=f"Merma extra {i}",
                    fk_decision=self.decision,
                    fk_producto_semanal=self.producto_semanal,
                )
                for i in range(page_size + 4)
            ]
        )
        # Total = 1 (setUp) + (page_size + 4) = page_size + 5
        expected_total = 1 + page_size + 4
        data = self._assert_success_envelope(self.client.get(reverse("merma-list")))
        self.assertEqual(data["count"], expected_total)
        self.assertEqual(len(data["results"]), page_size)
        self.assertIsNotNone(data["next"])
        self.assertIsNone(data["previous"])

    def test_agricultor_cannot_list_mermas(self):
        self.client.force_authenticate(self.agricultor)
        response = self.client.get(reverse("merma-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthorized_cannot_list_mermas(self):
        self.client.force_authenticate(None)
        response = self.client.get(reverse("merma-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ======================================================================
# CONCURRENCIA
# ======================================================================


class MermaConcurrencyTests(TransactionTestCase):
    """Verifica que select_for_update() previene race conditions en stock.

    Usa TransactionTestCase (no APITestCase) porque select_for_update()
    requiere transacciones reales de base de datos — APITestCase envuelve
    cada test en una transacción que bloquea el lock.
    """

    def setUp(self):
        super().setUp()

        patcher = patch("django.utils.timezone.localdate")
        self.mock_date = patcher.start()
        self.mock_date.return_value = date(2026, 7, 20)
        self.addCleanup(patcher.stop)

        self.admin = _create_user_with_role("Admin", "conc_admin")
        self.vendedor = _create_user_with_role("Vendedor", "conc_vendedor")

        self.categoria = CategoriaProducto.objects.create(nombre="Frutas", descripcion="Frutas", estado=True)
        self.producto = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            es_perecedero=True,
            estado=True,
        )
        self.unidad = Unidad.objects.create(nombre="Kilogramo", abreviatura="kg", tipo="Kilogramo", estado=True)
        self.decision = DecisionMerma.objects.create(decision="Donar")
        self.publicacion = PublicacionSemanal.objects.create(
            fk_agricultor=self.admin.usuario,
            fecha_publicacion=date(2026, 7, 20),
            semana=30,
            estado=PublicacionSemanal.ESTADO_PUBLICADO,
        )
        self.producto_semanal = ProductoSemanal.objects.create(
            fk_publicacion=self.publicacion,
            fk_producto=self.producto,
            fk_unidad=self.unidad,
            stock=10,
            precio="25.00",
            foto="http://example.com/foto.jpg",
            estado=ProductoSemanal.ESTADO_ACTIVO,
        )

    def test_concurrent_merma_race_condition(self):
        """Dos hilos intentan crear mermas que agotan stock. Solo una debe fallar.

        Stock=10. Dos hilos intentan crear mermas de 6 unidades cada uno.
        select_for_update() serializa el acceso: el primero descuenta,
        el segundo ve stock insuficiente y falla.
        """
        barrier = Barrier(2, timeout=30)
        results = []

        def _create():
            close_old_connections()
            client = APIClient()
            client.force_authenticate(self.vendedor)
            barrier.wait()  # Ambos hilos sincronizan antes de POST
            payload = {
                "fk_producto_semanal": self.producto_semanal.id_producto_semanal,
                "cantidad": 6,
                "motivo": "Concurrente",
                "fk_decision": self.decision.id_decision,
            }
            response = client.post(reverse("merma-list"), payload, format="json")
            results.append(response.status_code)

        threads = [Thread(target=_create) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 2)
        self.assertIn(status.HTTP_201_CREATED, results)
        self.assertIn(status.HTTP_400_BAD_REQUEST, results)

        # Verificar stock final
        self.producto_semanal.refresh_from_db()
        self.assertEqual(self.producto_semanal.stock, 4)  # 10 - 6 = 4


class MermaResumenTestCase(WasteBaseTestCase):
    """Tests para el endpoint de resumen de mermas."""

    def setUp(self):
        super().setUp()
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(self.admin)

        # Crear producto adicional
        self.producto2 = Producto.objects.create(
            nombre_producto="Pera",
            fk_categoria=self.categoria,
            es_perecedero=True,
            estado=True,
        )
        self.producto_semanal2 = ProductoSemanal.objects.create(
            fk_publicacion=self.publicacion,
            fk_producto=self.producto2,
            fk_unidad=self.unidad,
            stock=30,
            precio="30.00",
            estado=ProductoSemanal.ESTADO_ACTIVO,
        )
        self.decision2 = DecisionMerma.objects.create(decision="Desechar")

        # creado_en se setea con auto_now_add (timezone.now), no podemos
        # pasar valores explicitos. Todas quedan con la misma fecha/hora.
        Merma.objects.create(
            fk_producto_semanal=self.producto_semanal,
            cantidad=10,
            motivo="Sobreproducción",
            fk_decision=self.decision,
        )
        Merma.objects.create(
            fk_producto_semanal=self.producto_semanal,
            cantidad=5,
            motivo="Dañado",
            fk_decision=self.decision2,
        )
        Merma.objects.create(
            fk_producto_semanal=self.producto_semanal2,
            cantidad=8,
            motivo="Maduración excesiva",
            fk_decision=self.decision,
        )

    def test_acceso_no_autenticado(self):
        response = self.client.get(reverse("merma-resumen"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_acceso_sin_rol_admin(self):
        vendedor_client = APIClient()
        vendedor_client.force_authenticate(self.vendedor)
        response = vendedor_client.get(reverse("merma-resumen"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_resumen_sin_filtros(self):
        response = self.admin_client.get(reverse("merma-resumen"))
        self._assert_success_envelope(response)
        data = response.data["data"]
        self.assertEqual(data["agrupacion"], "mes")
        self.assertEqual(data["total_general"], 23)
        self.assertIsNotNone(data["producto_mas_afectado"])
        self.assertEqual(len(data["detalle"]), 3)

    def test_resumen_filtro_por_producto(self):
        response = self.admin_client.get(f"{reverse('merma-resumen')}?producto={self.producto.id_producto}")
        self._assert_success_envelope(response)
        data = response.data["data"]
        self.assertEqual(data["total_general"], 15)
        for row in data["detalle"]:
            self.assertEqual(row["producto_id"], self.producto.id_producto)

    def test_resumen_filtro_por_fecha(self):
        # creado_en es auto_now_add, así que actualizamos via query directa
        from datetime import datetime

        from django.utils import timezone

        mermas = Merma.objects.all().order_by("id_merma")
        fechas = [
            timezone.make_aware(datetime(2026, 7, 20, 10, 0, 0)),
            timezone.make_aware(datetime(2026, 7, 22, 10, 0, 0)),
            timezone.make_aware(datetime(2026, 7, 25, 10, 0, 0)),
        ]
        for merma, fecha in zip(mermas, fechas, strict=False):
            Merma.objects.filter(id_merma=merma.id_merma).update(creado_en=fecha)

        response = self.admin_client.get(f"{reverse('merma-resumen')}?fecha_desde=2026-07-23&fecha_hasta=2026-07-26")
        self._assert_success_envelope(response)
        data = response.data["data"]
        self.assertEqual(data["total_general"], 8)

    def test_resumen_agrupado_por_semana(self):
        response = self.admin_client.get(f"{reverse('merma-resumen')}?agrupar_por=semana")
        self._assert_success_envelope(response)
        data = response.data["data"]
        self.assertEqual(data["agrupacion"], "semana")
        self.assertEqual(data["total_general"], 23)

    def test_resumen_producto_mas_afectado(self):
        response = self.admin_client.get(reverse("merma-resumen"))
        self._assert_success_envelope(response)
        data = response.data["data"]
        self.assertEqual(data["producto_mas_afectado"]["nombre"], "Manzana")
        self.assertEqual(data["producto_mas_afectado"]["total"], 15)

    def test_resumen_sin_mermas(self):
        Merma.objects.all().delete()
        response = self.admin_client.get(reverse("merma-resumen"))
        self._assert_success_envelope(response)
        data = response.data["data"]
        self.assertEqual(data["total_general"], 0)
        self.assertIsNone(data["producto_mas_afectado"])
        self.assertEqual(len(data["detalle"]), 0)
