"""Tests para el módulo de Pagos."""

import threading
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase
from rest_framework import status
from rest_framework.test import APIClient

from rassa.models import (
    CategoriaProducto,
    DetallePedido,
    EstadoPedido,
    HistorialEstadoPedido,
    Pago,
    PedidoCabecera,
    Persona,
    Producto,
    ProductoSemanal,
    PublicacionSemanal,
    Recibo,
    Rol,
    TipoPago,
    Unidad,
    Usuario,
)


class PagosTestBase(TestCase):
    """Base class with shared setup for payment tests."""

    @classmethod
    def setUpTestData(cls):
        # Roles
        cls.rol_admin = Rol.objects.create(id_rol=1, nombre_rol="Admin", descripcion="Admin")
        cls.rol_vendedor = Rol.objects.create(id_rol=2, nombre_rol="Vendedor", descripcion="Vendedor")
        cls.rol_cliente = Rol.objects.create(id_rol=3, nombre_rol="Cliente", descripcion="Cliente")

        # Estados de pedido
        cls.estado_pendiente = EstadoPedido.objects.create(
            id_estado=1, tipo_estado="pendiente", descripcion="Pendiente"
        )
        cls.estado_confirmado = EstadoPedido.objects.create(
            id_estado=2, tipo_estado="confirmado", descripcion="Confirmado"
        )
        cls.estado_en_prep = EstadoPedido.objects.create(
            id_estado=3, tipo_estado="en_preparacion", descripcion="En preparación"
        )
        cls.estado_listo = EstadoPedido.objects.create(
            id_estado=4, tipo_estado="listo_para_retirar", descripcion="Listo para retirar"
        )
        cls.estado_entregado = EstadoPedido.objects.create(
            id_estado=5, tipo_estado="entregado", descripcion="Entregado"
        )
        cls.estado_cancelado = EstadoPedido.objects.create(
            id_estado=6, tipo_estado="cancelado", descripcion="Cancelado"
        )

        # Tipos de pago
        cls.tipo_efectivo = TipoPago.objects.create(id_tipo_pago=1, nombre="Efectivo")
        cls.tipo_transferencia = TipoPago.objects.create(id_tipo_pago=2, nombre="Transferencia")

        # Persona + Usuario vendedor
        cls.persona_vendedor = Persona.objects.create(
            nombre="Vendedor",
            apellido_paterno="Test",
            sexo="M",
            fecha_nacimiento="1990-01-01",
            domicilio="Calle 1",
        )
        cls.user_vendedor = User.objects.create_user(
            username="vendedor@test.com", email="vendedor@test.com", password="pass123"
        )
        cls.usuario_vendedor = Usuario.objects.create(
            fk_user=cls.user_vendedor,
            fk_persona=cls.persona_vendedor,
            fk_rol=cls.rol_vendedor,
            correo="vendedor@test.com",
        )

        # Persona + Usuario admin
        cls.persona_admin = Persona.objects.create(
            nombre="Admin",
            apellido_paterno="Test",
            sexo="M",
            fecha_nacimiento="1990-01-01",
            domicilio="Calle 2",
        )
        cls.user_admin = User.objects.create_user(username="admin@test.com", email="admin@test.com", password="pass123")
        cls.usuario_admin = Usuario.objects.create(
            fk_user=cls.user_admin,
            fk_persona=cls.persona_admin,
            fk_rol=cls.rol_admin,
            correo="admin@test.com",
        )

        # Persona + Usuario cliente
        cls.persona_cliente = Persona.objects.create(
            nombre="Cliente",
            apellido_paterno="Test",
            sexo="F",
            fecha_nacimiento="1995-05-15",
            domicilio="Calle 3",
        )
        cls.user_cliente = User.objects.create_user(
            username="cliente@test.com", email="cliente@test.com", password="pass123"
        )
        cls.usuario_cliente = Usuario.objects.create(
            fk_user=cls.user_cliente,
            fk_persona=cls.persona_cliente,
            fk_rol=cls.rol_cliente,
            correo="cliente@test.com",
        )

        # Catálogo para detalles de pedido
        cls.categoria = CategoriaProducto.objects.create(nombre="Verduras", descripcion="Verduras")
        cls.unidad = Unidad.objects.create(tipo="peso", nombre="Kilogramo", abreviatura="kg")
        cls.producto = Producto.objects.create(
            nombre_producto="Tomate",
            descripcion="Tomate rojo",
            fk_categoria=cls.categoria,
        )
        cls.publicacion = PublicacionSemanal.objects.create(
            fecha_publicacion="2026-07-26",
            semana=30,
            estado="publicado",
        )
        cls.producto_semanal = ProductoSemanal.objects.create(
            fk_publicacion=cls.publicacion,
            fk_producto=cls.producto,
            fk_unidad=cls.unidad,
            precio=Decimal("25.00"),
            stock=100,
        )

    def _crear_pedido(self, estado, vendedor=None):
        """Helper: crea un pedido con estado y detalles."""
        vend = vendedor or self.usuario_vendedor
        pedido = PedidoCabecera.objects.create(
            fk_cliente=self.usuario_cliente,
            fk_vendedor=vend,
            fk_estado=estado,
            subtotal=Decimal("100.00"),
            iva=Decimal("16.00"),
            total=Decimal("116.00"),
        )
        DetallePedido.objects.create(
            fk_pedido=pedido,
            fk_producto_semanal=self.producto_semanal,
            nombre_producto="Tomate",
            precio_unitario=Decimal("25.00"),
            cantidad=4,
            importe=Decimal("100.00"),
        )
        return pedido


class PagoCreateTest(PagosTestBase):
    """Tests de creación de pagos."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user_vendedor)

    def test_pago_exitoso(self):
        pedido = self._crear_pedido(self.estado_listo)
        resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()
        self.assertIn("folio", data)
        self.assertTrue(data["folio"].startswith("REC-"))
        self.assertEqual(data["monto"], "116.00")
        self.assertEqual(data["tipo_pago_nombre"], "Efectivo")

        # C-M3: el Recibo se expone en la respuesta del pago
        self.assertTrue(data["recibo_folio"].startswith("R-"))
        self.assertEqual(data["recibo_monto"], "116.00")

        # Pedido debe pasar a entregado
        pedido.refresh_from_db()
        self.assertEqual(pedido.fk_estado.tipo_estado, "entregado")

    def test_pago_crea_recibo(self):
        """Un pago exitoso genera un Recibo (B5)."""
        pedido = self._crear_pedido(self.estado_listo)
        resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        recibo = Recibo.objects.get(fk_pedido=pedido)
        self.assertEqual(recibo.monto, Decimal("116.00"))
        self.assertTrue(recibo.folio.startswith("R-"))
        self.assertEqual(recibo.fk_pago.fk_pedido, pedido)

    def test_folio_formato_correcto(self):
        pedido = self._crear_pedido(self.estado_listo)
        self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        pago = Pago.objects.last()
        # Format: REC-YYYYMMDD-001
        parts = pago.folio.split("-")
        self.assertEqual(parts[0], "REC")
        self.assertEqual(len(parts[1]), 8)  # YYYYMMDD
        self.assertEqual(len(parts[2]), 3)  # NNN

    def test_folio_secuencia_incrementa(self):
        p1 = self._crear_pedido(self.estado_listo)
        self.client.post(
            "/api/pagos/",
            {
                "pedido": p1.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        pago1 = Pago.objects.last()

        p2 = self._crear_pedido(self.estado_listo)
        self.client.post(
            "/api/pagos/",
            {
                "pedido": p2.id_pedido,
                "tipo_pago": self.tipo_transferencia.id_tipo_pago,
                "monto": "116.00",
            },
        )
        pago2 = Pago.objects.last()

        num1 = int(pago1.folio.split("-")[-1])
        num2 = int(pago2.folio.split("-")[-1])
        self.assertEqual(num2, num1 + 1)

    def test_pago_crea_historial_entregado(self):
        pedido = self._crear_pedido(self.estado_listo)
        self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        historial = HistorialEstadoPedido.objects.filter(fk_pedido=pedido).last()
        self.assertIsNotNone(historial)
        self.assertEqual(historial.fk_estado_anterior.tipo_estado, "listo_para_retirar")
        self.assertEqual(historial.fk_estado_nuevo.tipo_estado, "entregado")

    def test_pago_pedido_pendiente_falla(self):
        pedido = self._crear_pedido(self.estado_pendiente)
        resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pago_monto_incoincidente_no_avanza_estado(self):
        # La regla del serializer es de igualdad (abs(total-monto) > 0.001),
        # por lo que un monto distinto (menor o mayor) recorre el mismo camino.
        for monto in ("1.00", "117.00"):
            with self.subTest(monto=monto):
                pedido = self._crear_pedido(self.estado_listo)
                resp = self.client.post(
                    "/api/pagos/",
                    {
                        "pedido": pedido.id_pedido,
                        "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                        "monto": monto,
                    },
                )
                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertFalse(Pago.objects.filter(fk_pedido=pedido).exists())
                # El pedido no debe avanzar de estado pese al intento de pago fallido
                pedido.refresh_from_db()
                self.assertEqual(pedido.fk_estado.tipo_estado, "listo_para_retirar")

    def test_pago_pedido_cancelado_falla(self):
        pedido = self._crear_pedido(self.estado_cancelado)
        resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pago_pedido_entregado_falla(self):
        pedido = self._crear_pedido(self.estado_entregado)
        resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pago_duplicado_falla(self):
        pedido = self._crear_pedido(self.estado_listo)
        self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        # Second attempt on same pedido (now entregado)
        resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pago_pedido_inexistente_falla(self):
        resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": 99999,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pago_tipo_inexistente_falla(self):
        pedido = self._crear_pedido(self.estado_listo)
        resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": 99999,
                "monto": "116.00",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pago_monto_cero_falla(self):
        pedido = self._crear_pedido(self.estado_listo)
        resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "0.00",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pago_con_referencia(self):
        pedido = self._crear_pedido(self.estado_listo)
        resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_transferencia.id_tipo_pago,
                "monto": "116.00",
                "referencia": "TRANSF-12345",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()
        self.assertEqual(data["referencia"], "TRANSF-12345")

    def test_respuesta_incluye_detalles_pedido(self):
        pedido = self._crear_pedido(self.estado_listo)
        resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        data = resp.json()
        self.assertIn("productos", data)
        self.assertEqual(len(data["productos"]), 1)
        self.assertEqual(data["productos"][0]["nombre"], "Tomate")

    def test_admin_puede_crear_pago(self):
        self.client.force_authenticate(user=self.user_admin)
        pedido = self._crear_pedido(self.estado_listo)
        resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Pago.objects.filter(fk_pedido=pedido).exists())
        pago = Pago.objects.get(fk_pedido=pedido)
        self.assertTrue(pago.folio.startswith("REC-"))
        pedido.refresh_from_db()
        self.assertEqual(pedido.fk_estado.tipo_estado, "entregado")


class PagoPermisosTest(PagosTestBase):
    """Tests de permisos del endpoint de pagos."""

    def setUp(self):
        self.client = APIClient()

    def test_cliente_no_puede_crear_pago(self):
        self.client.force_authenticate(user=self.user_cliente)
        pedido = self._crear_pedido(self.estado_listo)
        resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_autenticado_falla(self):
        pedido = self._crear_pedido(self.estado_listo)
        resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_tipos_pago_sin_autenticacion_401(self):
        resp = self.client.get("/api/tipos-pago/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cliente_puede_ver_tipos_pago(self):
        self.client.force_authenticate(user=self.user_cliente)
        resp = self.client.get("/api/tipos-pago/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        nombres = [t["nombre"] for t in resp.json()]
        self.assertIn("Efectivo", nombres)
        self.assertIn("Transferencia", nombres)

    def test_vendedor_no_puede_pagar_pedido_de_otro_vendedor(self):
        persona2 = Persona.objects.create(
            nombre="Otro", apellido_paterno="Vendedor", sexo="M", fecha_nacimiento="1992-01-01", domicilio="Calle 4"
        )
        user2 = User.objects.create_user(username="vendedor2@test.com", email="vendedor2@test.com", password="pass123")
        usuario2 = Usuario.objects.create(
            fk_user=user2, fk_persona=persona2, fk_rol=self.rol_vendedor, correo="vendedor2@test.com"
        )
        pedido_otro = self._crear_pedido(self.estado_listo, vendedor=usuario2)

        self.client.force_authenticate(user=self.user_vendedor)
        resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido_otro.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_vendedor_no_puede_pagar_pedido_sin_vendedor(self):
        self.client.force_authenticate(user=self.user_vendedor)
        pedido = self._crear_pedido(self.estado_listo)
        pedido.fk_vendedor = None
        pedido.save(update_fields=["fk_vendedor"])
        resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_put_pago_retorna_405(self):
        self.client.force_authenticate(user=self.user_vendedor)
        resp = self.client.put("/api/pagos/1/", {"monto": "100.00"})
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_patch_pago_retorna_405(self):
        self.client.force_authenticate(user=self.user_vendedor)
        resp = self.client.patch("/api/pagos/1/", {"monto": "100.00"})
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_pago_retorna_405(self):
        self.client.force_authenticate(user=self.user_vendedor)
        resp = self.client.delete("/api/pagos/1/")
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_throttle_scopes_configured(self):
        """Verificar que los scopes de throttle existen en la configuracion."""
        from rassa.settings import REST_FRAMEWORK as rf

        self.assertIn("pagos_read", rf["DEFAULT_THROTTLE_RATES"])
        self.assertIn("pagos_write", rf["DEFAULT_THROTTLE_RATES"])


class PagoListTest(PagosTestBase):
    """Tests de listado y detalle de pagos."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user_vendedor)

    def test_listar_pagos_vacio(self):
        resp = self.client.get("/api/pagos/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["results"], [])

    def test_listar_pagos_con_datos(self):
        pedido = self._crear_pedido(self.estado_listo)
        self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        resp = self.client.get("/api/pagos/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertGreaterEqual(data["count"], 1)
        pedido_ids = [p["pedido"] for p in data["results"]]
        self.assertIn(pedido.id_pedido, pedido_ids)

    def test_detalle_pago(self):
        pedido = self._crear_pedido(self.estado_listo)
        create_resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        pago_id = create_resp.json()["id_pago"]
        resp = self.client.get(f"/api/pagos/{pago_id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["id_pago"], pago_id)
        self.assertIn("productos", data)

    def test_tipos_pago_endpoint(self):
        # El endpoint antiguo /api/pagos/tipos/ ya no existe (404)
        resp_old = self.client.get("/api/pagos/tipos/")
        self.assertEqual(resp_old.status_code, status.HTTP_404_NOT_FOUND)

        # El nuevo endpoint /api/tipos-pago/ debe retornar los tipos de pago
        resp = self.client.get("/api/tipos-pago/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        nombres = [t["nombre"] for t in resp.json()]
        self.assertIn("Efectivo", nombres)
        self.assertIn("Transferencia", nombres)

    def test_vendedor_solo_ve_sus_pagos(self):
        # Create another vendedor
        persona2 = Persona.objects.create(
            nombre="Otro", apellido_paterno="Vendedor", sexo="M", fecha_nacimiento="1992-01-01", domicilio="Calle 4"
        )
        user2 = User.objects.create_user(username="vendedor2@test.com", email="vendedor2@test.com", password="pass123")
        usuario2 = Usuario.objects.create(
            fk_user=user2, fk_persona=persona2, fk_rol=self.rol_vendedor, correo="vendedor2@test.com"
        )

        # Pedido assigned to another vendedor
        pedido_otro = self._crear_pedido(self.estado_listo, vendedor=usuario2)

        # Vendedor2 pays it
        client2 = APIClient()
        client2.force_authenticate(user=user2)
        client2.post(
            "/api/pagos/",
            {
                "pedido": pedido_otro.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )

        # Original vendedor should not see it
        resp = self.client.get("/api/pagos/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        results = data.get("results", data)
        pago_ids = [p["pedido"] for p in results]
        self.assertNotIn(pedido_otro.id_pedido, pago_ids)

    def test_filtrar_pagos_por_pedido(self):
        # Create two orders and pay them
        pedido1 = self._crear_pedido(self.estado_listo)
        self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido1.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        pago1 = Pago.objects.last()

        pedido2 = self._crear_pedido(self.estado_listo)
        self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido2.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        # Query all
        resp_all = self.client.get("/api/pagos/")
        self.assertEqual(resp_all.status_code, status.HTTP_200_OK)
        data_all = resp_all.json()
        results_all = data_all.get("results", data_all)
        self.assertTrue(len(results_all) >= 2)

        # Query filtered by pedido1
        resp_filtered = self.client.get(f"/api/pagos/?pedido={pedido1.id_pedido}")
        self.assertEqual(resp_filtered.status_code, status.HTTP_200_OK)
        data_filtered = resp_filtered.json()
        results_filtered = data_filtered.get("results", data_filtered)
        self.assertEqual(len(results_filtered), 1)
        self.assertEqual(results_filtered[0]["id_pago"], pago1.id_pago)

    def test_vendedor_no_puede_ver_detalle_pago_de_otro(self):
        persona2 = Persona.objects.create(
            nombre="Otro", apellido_paterno="Vendedor", sexo="M", fecha_nacimiento="1992-01-01", domicilio="Calle 4"
        )
        user2 = User.objects.create_user(username="vendedor2@test.com", email="vendedor2@test.com", password="pass123")
        usuario2 = Usuario.objects.create(
            fk_user=user2, fk_persona=persona2, fk_rol=self.rol_vendedor, correo="vendedor2@test.com"
        )
        pedido_otro = self._crear_pedido(self.estado_listo, vendedor=usuario2)

        # Vendedor2 pays it
        client2 = APIClient()
        client2.force_authenticate(user=user2)
        create_resp = client2.post(
            "/api/pagos/",
            {
                "pedido": pedido_otro.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        pago_id = create_resp.json()["id_pago"]

        # Original vendedor should NOT be able to see the detail
        resp = self.client.get(f"/api/pagos/{pago_id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        # Admin should be able to see any payment's detail
        admin_client = APIClient()
        admin_client.force_authenticate(user=self.user_admin)
        resp_admin = admin_client.get(f"/api/pagos/{pago_id}/")
        self.assertEqual(resp_admin.status_code, status.HTTP_200_OK)

    def test_listar_pagos_no_crashea_con_pedido_eliminado(self):
        # Create and then orphan the payment (simulate SET_NULL)
        pedido = self._crear_pedido(self.estado_listo)
        create_resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        pago_id = create_resp.json()["id_pago"]
        pago = Pago.objects.get(pk=pago_id)
        pago.fk_pedido = None
        pago.save(update_fields=["fk_pedido"])

        resp = self.client.get("/api/pagos/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_cliente_solo_ve_sus_pagos(self):
        # Pago del cliente propio
        pedido_propio = self._crear_pedido(self.estado_listo)
        self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido_propio.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        pago_propio = Pago.objects.get(fk_pedido=pedido_propio)

        # Otro cliente con su propio pago
        persona2 = Persona.objects.create(
            nombre="Otro", apellido_paterno="Cliente", sexo="F", fecha_nacimiento="1993-03-03", domicilio="Calle 5"
        )
        user2 = User.objects.create_user(username="cliente2@test.com", email="cliente2@test.com", password="pass123")
        usuario2 = Usuario.objects.create(
            fk_user=user2, fk_persona=persona2, fk_rol=self.rol_cliente, correo="cliente2@test.com"
        )
        pedido_ajeno = self._crear_pedido(self.estado_listo)
        pedido_ajeno.fk_cliente = usuario2
        pedido_ajeno.save(update_fields=["fk_cliente"])
        self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido_ajeno.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        pago_ajeno = Pago.objects.get(fk_pedido=pedido_ajeno)

        cliente_client = APIClient()
        cliente_client.force_authenticate(user=self.user_cliente)
        resp = cliente_client.get("/api/pagos/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        pago_ids = [p["id_pago"] for p in resp.json()["results"]]
        self.assertIn(pago_propio.id_pago, pago_ids)
        self.assertNotIn(pago_ajeno.id_pago, pago_ids)

    def test_cliente_puede_ver_pago_propio(self):
        pedido = self._crear_pedido(self.estado_listo)
        create_resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        pago_id = create_resp.json()["id_pago"]

        cliente_client = APIClient()
        cliente_client.force_authenticate(user=self.user_cliente)
        resp = cliente_client.get(f"/api/pagos/{pago_id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["id_pago"], pago_id)

    def test_cliente_no_puede_ver_pago_ajeno(self):
        persona2 = Persona.objects.create(
            nombre="Otro cliente",
            apellido_paterno="Cliente",
            sexo="F",
            fecha_nacimiento="1993-03-03",
            domicilio="Calle 5",
        )
        user2 = User.objects.create_user(username="cliente2@test.com", email="cliente2@test.com", password="pass123")
        usuario2 = Usuario.objects.create(
            fk_user=user2, fk_persona=persona2, fk_rol=self.rol_cliente, correo="cliente2@test.com"
        )
        pedido_ajeno = self._crear_pedido(self.estado_listo)
        pedido_ajeno.fk_cliente = usuario2
        pedido_ajeno.save(update_fields=["fk_cliente"])
        create_resp = self.client.post(
            "/api/pagos/",
            {
                "pedido": pedido_ajeno.id_pedido,
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "monto": "116.00",
            },
        )
        pago_id = create_resp.json()["id_pago"]

        # El cliente logueado no debe ver el detalle de un pago de otro cliente
        cliente_client = APIClient()
        cliente_client.force_authenticate(user=self.user_cliente)
        resp = cliente_client.get(f"/api/pagos/{pago_id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class PagoConcurrencyTest(TransactionTestCase):
    """Test de concurrencia para generación de folios."""

    def setUp(self):
        # Minimal shared setup (TransactionTestCase resets DB between tests)
        self.rol_vendedor = Rol.objects.create(id_rol=2, nombre_rol="Vendedor", descripcion="Vendedor")
        self.estado_listo = EstadoPedido.objects.create(
            id_estado=4, tipo_estado="listo_para_retirar", descripcion="Listo para retirar"
        )
        self.estado_entregado = EstadoPedido.objects.create(
            id_estado=5, tipo_estado="entregado", descripcion="Entregado"
        )
        self.tipo_efectivo = TipoPago.objects.create(id_tipo_pago=1, nombre="Efectivo")

        persona = Persona.objects.create(
            nombre="Vendedor",
            apellido_paterno="Conc",
            sexo="M",
            fecha_nacimiento="1990-01-01",
            domicilio="Calle 1",
        )
        user = User.objects.create_user(username="vend@conc.test", email="vend@conc.test", password="pass")
        self.usuario = Usuario.objects.create(
            fk_user=user,
            fk_persona=persona,
            fk_rol=self.rol_vendedor,
            correo="vend@conc.test",
        )

        self.categoria = CategoriaProducto.objects.create(nombre="Verduras", descripcion="Verduras")
        self.unidad = Unidad.objects.create(tipo="peso", nombre="Kilogramo", abreviatura="kg")
        producto = Producto.objects.create(
            nombre_producto="Tomate", descripcion="Tomate rojo", fk_categoria=self.categoria
        )
        publicacion = PublicacionSemanal.objects.create(
            fecha_publicacion="2026-07-28",
            semana=31,
            estado="publicado",
        )
        self.producto_semanal = ProductoSemanal.objects.create(
            fk_publicacion=publicacion,
            fk_producto=producto,
            fk_unidad=self.unidad,
            precio=Decimal("25.00"),
            stock=100,
        )

    def _crear_pedido(self):
        pedido = PedidoCabecera.objects.create(
            fk_cliente=self.usuario,
            fk_vendedor=self.usuario,
            fk_estado=self.estado_listo,
            subtotal=Decimal("100.00"),
            iva=Decimal("16.00"),
            total=Decimal("116.00"),
        )
        DetallePedido.objects.create(
            fk_pedido=pedido,
            fk_producto_semanal=self.producto_semanal,
            nombre_producto="Tomate",
            precio_unitario=Decimal("25.00"),
            cantidad=4,
            importe=Decimal("100.00"),
        )
        return pedido

    def test_folio_no_duplicado_bajo_concurrencia(self):
        NUM_THREADS = 5
        pedidos = [self._crear_pedido() for _ in range(NUM_THREADS)]
        results = []
        barrier = threading.Barrier(NUM_THREADS)

        def pay(pedido):
            client = APIClient()
            client.force_authenticate(user=self.usuario.fk_user)
            barrier.wait()
            resp = client.post(
                "/api/pagos/",
                {"pedido": pedido.id_pedido, "tipo_pago": self.tipo_efectivo.id_tipo_pago, "monto": "116.00"},
            )
            results.append(resp.status_code)

        threads = [threading.Thread(target=pay, args=(p,)) for p in pedidos]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), NUM_THREADS)
        self.assertNotIn(status.HTTP_500_INTERNAL_SERVER_ERROR, results)
        self.assertNotIn(status.HTTP_409_CONFLICT, results)
        self.assertEqual(sum(1 for r in results if r == status.HTTP_201_CREATED), NUM_THREADS)

        folios = list(Pago.objects.values_list("folio", flat=True))
        self.assertEqual(len(folios), NUM_THREADS)
        self.assertEqual(len(set(folios)), NUM_THREADS, "Folios duplicados bajo concurrencia")

    def test_doble_pago_concurrente_mismo_pedido(self):
        """Doble pago concurrente del MISMO pedido: solo 1 pago sobrevive.

        La rama select_for_update + re-validación bajo lock (pagos/views.py) debe
        garantizar: exactamente 1x201, N-1x400, 0x500, y la invariante
        (1 Pago + 1 Recibo + pedido entregado).
        """
        NUM_THREADS = 4
        pedido = self._crear_pedido()
        results = []
        barrier = threading.Barrier(NUM_THREADS)

        def pay():
            client = APIClient()
            client.force_authenticate(user=self.usuario.fk_user)
            barrier.wait()
            resp = client.post(
                "/api/pagos/",
                {"pedido": pedido.id_pedido, "tipo_pago": self.tipo_efectivo.id_tipo_pago, "monto": "116.00"},
            )
            results.append(resp.status_code)

        threads = [threading.Thread(target=pay) for _ in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), NUM_THREADS)
        self.assertEqual(sum(1 for r in results if r == status.HTTP_201_CREATED), 1, "Solo un pago debe tener exito")
        self.assertEqual(
            sum(1 for r in results if r == status.HTTP_400_BAD_REQUEST), NUM_THREADS - 1, "El resto debe ser 400"
        )
        self.assertNotIn(status.HTTP_500_INTERNAL_SERVER_ERROR, results)

        # Invariante: 1 Pago + 1 Recibo + pedido entregado
        self.assertEqual(Pago.objects.filter(fk_pedido=pedido).count(), 1)
        self.assertEqual(Recibo.objects.filter(fk_pedido=pedido).count(), 1)
        pedido.refresh_from_db()
        self.assertEqual(pedido.fk_estado.tipo_estado, "entregado")


class PagoConstraintRegresionTest(TestCase):
    """Tests de regresión para la migración 0018 (cambio nulls_distinct en Pago).

    El constraint `unique_pago_per_pedido` cambió de `nulls_distinct=False` a
    `nulls_distinct=True` para permitir múltiples Pagos con `fk_pedido=NULL`
    (pagos de liquidación RASSA→agricultor). Este test blinda ese cambio.
    """

    def setUp(self):
        # No necesitamos usuarios completos — solo verificar el nivel de BD.
        self.rol = Rol.objects.create(nombre_rol="Vendedor", descripcion="Vendedor")
        self.persona = Persona.objects.create(
            nombre="Test",
            apellido_paterno="X",
            sexo="M",
            fecha_nacimiento="1990-01-01",
            domicilio="Calle 1",
        )
        self.user = User.objects.create_user(
            username="regresion@test.com", email="regresion@test.com", password="pass123"
        )
        self.tipo = TipoPago.objects.create(nombre="Efectivo")

    def test_multiples_pagos_con_fk_pedido_null_coexisten(self):
        """Crear 3 Pagos con fk_pedido=NULL no debe violar el constraint."""
        for i in range(3):
            Pago.objects.create(
                fk_pedido=None,
                fk_tipo=self.tipo,
                monto=Decimal("100.00"),
                referencia=f"REF-{i}",
            )
        self.assertEqual(Pago.objects.filter(fk_pedido__isnull=True).count(), 3)

    def test_un_pago_por_pedido_NO_NULL_sigue_intacto(self):
        """Crea 2 Pagos con el mismo fk_pedido NO NULL. El segundo debe
        fallar con IntegrityError — el constraint sigue garantizando
        "un pago por pedido" cuando fk_pedido IS NOT NULL (revisión 4R
        R3 SUGGESTION sobre la regresión 0018)."""

        # Setup mínimo: un pedido en estado "listo_para_retirar"
        estado_listo = EstadoPedido.objects.create(tipo_estado="listo_para_retirar", descripcion="Listo")
        pedido = PedidoCabecera.objects.create(
            fk_estado=estado_listo,
            subtotal=Decimal("100.00"),
            iva=Decimal("0.00"),
            total=Decimal("100.00"),
        )

        # Primer pago: OK (atomic bloquea la transacción de TestCase para
        # que el IntegrityError del 2do no la aborte).
        with transaction.atomic():
            Pago.objects.create(fk_pedido=pedido, fk_tipo=self.tipo, monto=Decimal("100.00"))

            # Segundo pago con el mismo pedido: debe violar el constraint.
            # Savepoint interno para que el catch limpie el error sin afectar
            # la transacción externa.
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    Pago.objects.create(fk_pedido=pedido, fk_tipo=self.tipo, monto=Decimal("100.00"))

        # Coexisten: 1 con fk_pedido + 1 con fk_pedido=None
        Pago.objects.create(fk_pedido=None, fk_tipo=self.tipo, monto=Decimal("50.00"))
        self.assertEqual(Pago.objects.count(), 2)
        self.assertEqual(Pago.objects.filter(fk_pedido__isnull=True).count(), 1)
        self.assertEqual(Pago.objects.filter(fk_pedido__isnull=False).count(), 1)
