"""Pruebas para el módulo de Liquidaciones."""

import threading
import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import OperationalError, connection
from django.test import TransactionTestCase
from django.utils import timezone as dj_timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from rassa.models import (
    CategoriaProducto,
    DetallePedido,
    EstadoPedido,
    Liquidacion,
    Pago,
    PedidoCabecera,
    Persona,
    Producto,
    ProductoSemanal,
    PublicacionSemanal,
    Rol,
    TipoPago,
    Unidad,
    Usuario,
)


def _aware(year, month, day, hour=12, minute=0):
    """Datetime aware en zona local del proyecto (America/Argentina/Buenos_Aires)."""
    tz = dj_timezone.get_current_timezone()
    return datetime(year, month, day, hour, minute, tzinfo=tz)


class LiquidacionesTestBase(APITestCase):
    """Datos base: roles, usuarios, catálogo, publicaciones, productos."""

    def setUp(self):
        self.rol_admin = Rol.objects.create(nombre_rol="Admin", descripcion="Administrador")
        self.rol_vendedor = Rol.objects.create(nombre_rol="Vendedor", descripcion="Vendedor")
        self.rol_cliente = Rol.objects.create(nombre_rol="Cliente", descripcion="Cliente")
        self.rol_agricultor = Rol.objects.create(nombre_rol="Agricultor", descripcion="Agricultor")

        self.estado_entregado = EstadoPedido.objects.create(tipo_estado="entregado", descripcion="Entregado")
        self.estado_listo = EstadoPedido.objects.create(
            tipo_estado="listo_para_retirar", descripcion="Listo para retirar"
        )
        self.estado_confirmado = EstadoPedido.objects.create(tipo_estado="confirmado", descripcion="Confirmado")

        self.tipo_efectivo = TipoPago.objects.create(nombre="Efectivo")
        self.tipo_transferencia = TipoPago.objects.create(nombre="Transferencia")

        self._crear_usuarios()
        self._crear_catalogo()

        self.publicacion = PublicacionSemanal.objects.create(
            fk_agricultor=self.usuario_agricultor,
            fecha_publicacion=date(2026, 7, 20),
            semana=30,
            estado="publicado",
        )
        self.producto_semanal = ProductoSemanal.objects.create(
            fk_publicacion=self.publicacion,
            fk_producto=self.producto,
            fk_unidad=self.unidad,
            precio=Decimal("25.00"),
            stock=500,
        )

    def _crear_usuarios(self):
        self.persona_admin = Persona.objects.create(
            nombre="Admin",
            apellido_paterno="Rassa",
            fecha_nacimiento="1990-01-01",
            sexo="M",
            domicilio="Calle 1",
        )
        self.user_admin = User.objects.create_user(
            username="admin@test.com", email="admin@test.com", password="pass123"
        )
        self.usuario_admin = Usuario.objects.create(
            fk_user=self.user_admin,
            fk_persona=self.persona_admin,
            telefono="111",
            correo="admin@test.com",
            fk_rol=self.rol_admin,
        )

        self.persona_vendedor = Persona.objects.create(
            nombre="Vend",
            apellido_paterno="Uno",
            fecha_nacimiento="1985-03-10",
            sexo="M",
            domicilio="Calle 2",
        )
        self.user_vendedor = User.objects.create_user(
            username="vendedor@test.com", email="vendedor@test.com", password="pass123"
        )
        self.usuario_vendedor = Usuario.objects.create(
            fk_user=self.user_vendedor,
            fk_persona=self.persona_vendedor,
            telefono="222",
            correo="vendedor@test.com",
            fk_rol=self.rol_vendedor,
        )

        self.persona_cliente = Persona.objects.create(
            nombre="Cli",
            apellido_paterno="Uno",
            fecha_nacimiento="1995-05-05",
            sexo="F",
            domicilio="Calle 3",
        )
        self.user_cliente = User.objects.create_user(
            username="cliente@test.com", email="cliente@test.com", password="pass123"
        )
        self.usuario_cliente = Usuario.objects.create(
            fk_user=self.user_cliente,
            fk_persona=self.persona_cliente,
            telefono="333",
            correo="cliente@test.com",
            fk_rol=self.rol_cliente,
        )

        self.persona_agricultor = Persona.objects.create(
            nombre="Agri",
            apellido_paterno="Uno",
            fecha_nacimiento="1980-07-15",
            sexo="M",
            domicilio="Rancho 1",
        )
        self.user_agricultor = User.objects.create_user(
            username="agricultor@test.com", email="agricultor@test.com", password="pass123"
        )
        self.usuario_agricultor = Usuario.objects.create(
            fk_user=self.user_agricultor,
            fk_persona=self.persona_agricultor,
            telefono="444",
            correo="agricultor@test.com",
            fk_rol=self.rol_agricultor,
        )

    def _crear_catalogo(self):
        self.categoria = CategoriaProducto.objects.create(nombre="Verduras", descripcion="Verduras")
        self.unidad = Unidad.objects.create(tipo="peso", nombre="Kilogramo", abreviatura="kg")
        self.producto = Producto.objects.create(
            nombre_producto="Tomate",
            descripcion="Tomate rojo",
            fk_categoria=self.categoria,
            fk_unidad=self.unidad,
            precio=Decimal("25.00"),
            stock=1000,
        )

    def _crear_pedido_entregado(self, total=Decimal("100.00"), creado_en=None, con_pago=True):
        pedido = PedidoCabecera.objects.create(
            fk_cliente=self.usuario_cliente,
            fk_estado=self.estado_entregado,
            fk_vendedor=self.usuario_vendedor,
            subtotal=total,
            iva=Decimal("0.00"),
            total=total,
        )
        if creado_en is not None:
            PedidoCabecera.objects.filter(pk=pedido.pk).update(creado_en=creado_en)
            pedido.refresh_from_db()
        DetallePedido.objects.create(
            fk_pedido=pedido,
            fk_producto_semanal=self.producto_semanal,
            nombre_producto="Tomate",
            precio_unitario=Decimal("25.00"),
            cantidad=4,
            importe=total,
        )
        if con_pago:
            Pago.objects.create(
                fk_pedido=pedido,
                fk_tipo=self.tipo_efectivo,
                monto=total,
            )
        return pedido

    def _calcular(self, agricultor_id=None, semana=30, anio=2026, client=None, **extra_data):
        """Helper para realizar peticiones POST /api/liquidaciones/calcular/."""
        c = client or self.client
        data = {
            "agricultor": agricultor_id if agricultor_id is not None else self.usuario_agricultor.id_usuario,
            "semana": semana,
            "anio": anio,
        }
        data.update(extra_data)
        return c.post("/api/liquidaciones/calcular/", data, format="json")


class CalcularLiquidacionTest(LiquidacionesTestBase):
    """Cálculo de liquidaciones semanales por agricultor."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user_admin)

    def test_calcular_con_tres_ventas_calcula_total_y_comision(self):
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))
        self._crear_pedido_entregado(total=Decimal("200.00"), creado_en=_aware(2026, 7, 23))
        self._crear_pedido_entregado(total=Decimal("300.00"), creado_en=_aware(2026, 7, 26, hour=10))

        resp = self._calcular()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        body = resp.json()
        self.assertEqual(body["ok"], True)
        data = body["data"]
        self.assertEqual(Decimal(data["monto_ventas"]), Decimal("600.00"))
        self.assertEqual(Decimal(data["comision"]), Decimal("60.00"))
        self.assertEqual(Decimal(data["monto_liquidar"]), Decimal("540.00"))
        self.assertEqual(data["estado"], "pendiente")
        self.assertEqual(data["agricultor_id"], self.usuario_agricultor.id_usuario)
        self.assertEqual(data["agricultor_nombre"], "Agri Uno")
        self.assertEqual(len(data["ventas"]), 3)

    def test_calcular_respeta_frontera_de_semana(self):
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 19))
        self._crear_pedido_entregado(total=Decimal("200.00"), creado_en=_aware(2026, 7, 20))
        self._crear_pedido_entregado(total=Decimal("300.00"), creado_en=_aware(2026, 7, 26, hour=23))
        self._crear_pedido_entregado(total=Decimal("999.00"), creado_en=_aware(2026, 7, 27))

        resp = self._calcular()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()["data"]
        # Solo entran los 2 pedidos de la semana 30 (lun 2026-07-20 a dom 2026-07-26 inclusive)
        self.assertEqual(Decimal(data["monto_ventas"]), Decimal("500.00"))
        self.assertEqual(len(data["ventas"]), 2)

    def test_calcular_sin_ventas_retorna_400(self):
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("No hay ventas", resp.json()["message"])

    def test_calcular_solo_cuenta_pedidos_entregados(self):
        self._crear_pedido_entregado(total=Decimal("500.00"), creado_en=_aware(2026, 7, 21))
        # Pedido NO entregado: no debe contar
        pedido_confirmado = PedidoCabecera.objects.create(
            fk_cliente=self.usuario_cliente,
            fk_estado=self.estado_confirmado,
            fk_vendedor=self.usuario_vendedor,
            subtotal=Decimal("999.00"),
            iva=Decimal("0.00"),
            total=Decimal("999.00"),
        )
        PedidoCabecera.objects.filter(pk=pedido_confirmado.pk).update(creado_en=_aware(2026, 7, 22))
        DetallePedido.objects.create(
            fk_pedido=pedido_confirmado,
            fk_producto_semanal=self.producto_semanal,
            nombre_producto="Tomate",
            precio_unitario=Decimal("25.00"),
            cantidad=40,
            importe=Decimal("999.00"),
        )

        resp = self._calcular()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()["data"]
        self.assertEqual(Decimal(data["monto_ventas"]), Decimal("500.00"))
        self.assertEqual(len(data["ventas"]), 1)

    def test_calcular_no_cuenta_pedidos_de_otro_agricultor(self):
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))

        # Crear un segundo agricultor con su propia publicación y producto
        persona_otro = Persona.objects.create(
            nombre="Otro",
            apellido_paterno="Agri",
            fecha_nacimiento="1982-01-01",
            sexo="M",
            domicilio="Rancho 2",
        )
        user_otro = User.objects.create_user(
            username="agricultor2@test.com", email="agricultor2@test.com", password="pass123"
        )
        usuario_otro = Usuario.objects.create(
            fk_user=user_otro,
            fk_persona=persona_otro,
            telefono="555",
            correo="agricultor2@test.com",
            fk_rol=self.rol_agricultor,
        )
        publicacion_otro = PublicacionSemanal.objects.create(
            fk_agricultor=usuario_otro,
            fecha_publicacion=date(2026, 7, 20),
            semana=30,
            estado="publicado",
        )
        producto_semanal_otro = ProductoSemanal.objects.create(
            fk_publicacion=publicacion_otro,
            fk_producto=self.producto,
            fk_unidad=self.unidad,
            precio=Decimal("50.00"),
            stock=200,
        )
        pedido_otro = PedidoCabecera.objects.create(
            fk_cliente=self.usuario_cliente,
            fk_estado=self.estado_entregado,
            fk_vendedor=self.usuario_vendedor,
            subtotal=Decimal("777.00"),
            iva=Decimal("0.00"),
            total=Decimal("777.00"),
        )
        PedidoCabecera.objects.filter(pk=pedido_otro.pk).update(creado_en=_aware(2026, 7, 22))
        DetallePedido.objects.create(
            fk_pedido=pedido_otro,
            fk_producto_semanal=producto_semanal_otro,
            nombre_producto="Tomate",
            precio_unitario=Decimal("50.00"),
            cantidad=15,
            importe=Decimal("777.00"),
        )

        # Calcular para el primer agricultor: solo debe contar el pedido de 100
        resp = self._calcular()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()["data"]
        self.assertEqual(Decimal(data["monto_ventas"]), Decimal("100.00"))

    def test_calcular_con_tasa_personalizada(self):
        self._crear_pedido_entregado(total=Decimal("1000.00"), creado_en=_aware(2026, 7, 21))

        with patch("rassa.blueprints.liquidaciones.views.COMISION_RASSA", new=Decimal("0.05")):
            resp = self._calcular()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()["data"]
        self.assertEqual(Decimal(data["monto_ventas"]), Decimal("1000.00"))
        self.assertEqual(Decimal(data["comision"]), Decimal("50.00"))
        self.assertEqual(Decimal(data["monto_liquidar"]), Decimal("950.00"))

    def test_calcular_bloquea_duplicado_409(self):
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))

        resp1 = self._calcular()
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)

        resp2 = self._calcular()
        self.assertEqual(resp2.status_code, status.HTTP_409_CONFLICT)
        body = resp2.json()
        self.assertEqual(body["data"]["id_liquidacion_existente"], resp1.json()["data"]["id_liquidacion"])

    def test_agricultor_invalido_retorna_400(self):
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {"agricultor": 999999, "semana": 30, "anio": 2026},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_agricultor_que_no_es_agricultor_retorna_400(self):
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_cliente.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_semana_invalida_retorna_400(self):
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 54,
                "anio": 2026,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class MarcarPagadaTest(LiquidacionesTestBase):
    """Marcar liquidación como pagada."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user_admin)
        self._crear_pedido_entregado(total=Decimal("500.00"), creado_en=_aware(2026, 7, 21))

        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        self.liquidacion_id = resp.json()["data"]["id_liquidacion"]

    def test_marcar_pagada_crea_pago_y_actualiza_estado(self):
        resp = self.client.post(
            f"/api/liquidaciones/{self.liquidacion_id}/marcar-pagada/",
            {"tipo_pago": self.tipo_transferencia.id_tipo_pago, "referencia": "TRANSF-001"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()["data"]
        self.assertEqual(data["estado"], "pagada")
        self.assertIsNotNone(data["pago_liquidacion"])
        self.assertEqual(data["pago_liquidacion"]["tipo_pago_nombre"], "Transferencia")
        self.assertEqual(data["pago_liquidacion"]["referencia"], "TRANSF-001")
        self.assertTrue(data["pago_liquidacion"]["folio"].startswith("REC-"))

        # Pago creado con fk_pedido NULL y monto correcto
        pago = Pago.objects.get(id_pago=data["pago_liquidacion"]["id_pago"])
        self.assertIsNone(pago.fk_pedido)
        self.assertEqual(pago.monto, Decimal("450.00"))  # 500 - 10% = 450

    def test_marcar_pagada_sin_referencia_es_valido(self):
        resp = self.client.post(
            f"/api/liquidaciones/{self.liquidacion_id}/marcar-pagada/",
            {"tipo_pago": self.tipo_efectivo.id_tipo_pago},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["data"]["pago_liquidacion"]["referencia"], "")

    def test_marcar_pagada_sobre_ya_pagada_es_idempotente_200(self):
        self.client.post(
            f"/api/liquidaciones/{self.liquidacion_id}/marcar-pagada/",
            {"tipo_pago": self.tipo_efectivo.id_tipo_pago},
            format="json",
        )
        resp2 = self.client.post(
            f"/api/liquidaciones/{self.liquidacion_id}/marcar-pagada/",
            {"tipo_pago": self.tipo_efectivo.id_tipo_pago},
            format="json",
        )
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)

    def test_marcar_pagada_tipo_pago_inexistente_retorna_400(self):
        resp = self.client.post(
            f"/api/liquidaciones/{self.liquidacion_id}/marcar-pagada/",
            {"tipo_pago": 99999},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_marcar_pagada_liquidacion_inexistente_retorna_404(self):
        resp = self.client.post(
            "/api/liquidaciones/99999/marcar-pagada/",
            {"tipo_pago": self.tipo_efectivo.id_tipo_pago},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_dos_liquidaciones_se_pagan_con_pagos_distintos(self):
        # Segunda liquidación: semana 31 con su propia venta
        publicacion2 = PublicacionSemanal.objects.create(
            fk_agricultor=self.usuario_agricultor,
            fecha_publicacion=date(2026, 7, 27),
            semana=31,
            estado="publicado",
        )
        producto_semanal2 = ProductoSemanal.objects.create(
            fk_publicacion=publicacion2,
            fk_producto=self.producto,
            fk_unidad=self.unidad,
            precio=Decimal("25.00"),
            stock=200,
        )
        pedido2 = PedidoCabecera.objects.create(
            fk_cliente=self.usuario_cliente,
            fk_estado=self.estado_entregado,
            fk_vendedor=self.usuario_vendedor,
            subtotal=Decimal("200.00"),
            iva=Decimal("0.00"),
            total=Decimal("200.00"),
        )
        PedidoCabecera.objects.filter(pk=pedido2.pk).update(creado_en=_aware(2026, 7, 28))
        DetallePedido.objects.create(
            fk_pedido=pedido2,
            fk_producto_semanal=producto_semanal2,
            nombre_producto="Tomate",
            precio_unitario=Decimal("25.00"),
            cantidad=8,
            importe=Decimal("200.00"),
        )

        resp2 = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 31,
                "anio": 2026,
            },
            format="json",
        )
        liquidacion2_id = resp2.json()["data"]["id_liquidacion"]

        # Pagar ambas
        r1 = self.client.post(
            f"/api/liquidaciones/{self.liquidacion_id}/marcar-pagada/",
            {"tipo_pago": self.tipo_efectivo.id_tipo_pago},
            format="json",
        )
        r2 = self.client.post(
            f"/api/liquidaciones/{liquidacion2_id}/marcar-pagada/",
            {"tipo_pago": self.tipo_transferencia.id_tipo_pago},
            format="json",
        )
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        self.assertEqual(r2.status_code, status.HTTP_200_OK)

        pagos_sin_pedido = Pago.objects.filter(fk_pedido__isnull=True)
        self.assertEqual(pagos_sin_pedido.count(), 2)


class LiquidacionListTest(LiquidacionesTestBase):
    """Listar y filtrar liquidaciones."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user_admin)
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))
        self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )

    def test_listar_retorna_liquidaciones_envueltas(self):
        resp = self.client.get("/api/liquidaciones/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body["ok"], True)
        self.assertIn("results", body["data"])
        self.assertEqual(len(body["data"]["results"]), 1)

    def test_filtro_por_agricultor(self):
        resp = self.client.get(f"/api/liquidaciones/?agricultor={self.usuario_agricultor.id_usuario}")
        self.assertEqual(len(resp.json()["data"]["results"]), 1)

        resp_empty = self.client.get(f"/api/liquidaciones/?agricultor={self.usuario_cliente.id_usuario}")
        self.assertEqual(len(resp_empty.json()["data"]["results"]), 0)

    def test_filtro_por_estado(self):
        resp = self.client.get("/api/liquidaciones/?estado=pendiente")
        self.assertEqual(len(resp.json()["data"]["results"]), 1)
        resp_empty = self.client.get("/api/liquidaciones/?estado=pagada")
        self.assertEqual(len(resp_empty.json()["data"]["results"]), 0)

    def test_detalle_incluye_ventas_y_pago_liquidacion_null(self):
        liquidacion_id = Liquidacion.objects.first().id_liquidacion
        resp = self.client.get(f"/api/liquidaciones/{liquidacion_id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()["data"]
        self.assertIn("ventas", data)
        self.assertEqual(len(data["ventas"]), 1)
        # Verificamos que el pedido referenciado es el de 100.00 que creamos
        self.assertEqual(Decimal(data["ventas"][0]["total"]), Decimal("100.00"))
        self.assertEqual(data["ventas"][0]["cliente_nombre"], "Cli Uno")
        self.assertIsNone(data["pago_liquidacion"])


class PermisosTest(LiquidacionesTestBase):
    """Permisos: solo Admin puede ver/operar liquidaciones."""

    def setUp(self):
        super().setUp()
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))

    def _calcular(self):
        # helper para crear una liquidación como admin
        client = APIClient()
        client.force_authenticate(user=self.user_admin)
        return client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )

    def test_vendedor_no_puede_listar(self):
        self.client.force_authenticate(user=self.user_vendedor)
        resp = self.client.get("/api/liquidaciones/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cliente_no_puede_listar(self):
        self.client.force_authenticate(user=self.user_cliente)
        resp = self.client.get("/api/liquidaciones/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_agricultor_no_puede_listar(self):
        self.client.force_authenticate(user=self.user_agricultor)
        resp = self.client.get("/api/liquidaciones/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_autenticado_retorna_401(self):
        resp = self.client.get("/api/liquidaciones/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_vendedor_no_puede_calcular(self):
        self.client.force_authenticate(user=self.user_vendedor)
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_vendedor_no_puede_marcar_pagada(self):
        resp = self._calcular()
        liquidacion_id = resp.json()["data"]["id_liquidacion"]

        self.client.force_authenticate(user=self.user_vendedor)
        resp2 = self.client.post(
            f"/api/liquidaciones/{liquidacion_id}/marcar-pagada/",
            {"tipo_pago": self.tipo_efectivo.id_tipo_pago},
            format="json",
        )
        self.assertEqual(resp2.status_code, status.HTTP_403_FORBIDDEN)

    def test_cliente_no_puede_calcular(self):
        self.client.force_authenticate(user=self.user_cliente)
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_agricultor_no_puede_calcular(self):
        self.client.force_authenticate(user=self.user_agricultor)
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cliente_no_puede_marcar_pagada(self):
        self.client.force_authenticate(user=self.user_admin)
        resp = self._calcular()
        liquidacion_id = resp.json()["data"]["id_liquidacion"]

        self.client.force_authenticate(user=self.user_cliente)
        resp2 = self.client.post(
            f"/api/liquidaciones/{liquidacion_id}/marcar-pagada/",
            {"tipo_pago": self.tipo_efectivo.id_tipo_pago},
            format="json",
        )
        self.assertEqual(resp2.status_code, status.HTTP_403_FORBIDDEN)

    def test_agricultor_no_puede_marcar_pagada(self):
        self.client.force_authenticate(user=self.user_admin)
        resp = self._calcular()
        liquidacion_id = resp.json()["data"]["id_liquidacion"]

        self.client.force_authenticate(user=self.user_agricultor)
        resp2 = self.client.post(
            f"/api/liquidaciones/{liquidacion_id}/marcar-pagada/",
            {"tipo_pago": self.tipo_efectivo.id_tipo_pago},
            format="json",
        )
        self.assertEqual(resp2.status_code, status.HTTP_403_FORBIDDEN)

    def test_cliente_y_agricultor_no_pueden_consultar_detalle(self):
        resp = self._calcular()
        liquidacion_id = resp.json()["data"]["id_liquidacion"]

        for u in (self.user_cliente, self.user_agricultor):
            self.client.force_authenticate(user=u)
            resp_get = self.client.get(f"/api/liquidaciones/{liquidacion_id}/")
            self.assertEqual(resp_get.status_code, status.HTTP_403_FORBIDDEN)


class CalcularEdgeCasesTest(LiquidacionesTestBase):
    """Casos borde de cálculo (tasa 0/1, default, semana inválida, 409 con id)."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user_admin)

    def test_tasa_comision_cero_calcula_sin_comision(self):
        self._crear_pedido_entregado(total=Decimal("500.00"), creado_en=_aware(2026, 7, 21))

        with patch("rassa.blueprints.liquidaciones.views.COMISION_RASSA", new=Decimal("0.00")):
            resp = self.client.post(
                "/api/liquidaciones/calcular/",
                {
                    "agricultor": self.usuario_agricultor.id_usuario,
                    "semana": 30,
                    "anio": 2026,
                },
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()["data"]
        self.assertEqual(Decimal(data["monto_ventas"]), Decimal("500.00"))
        self.assertEqual(Decimal(data["comision"]), Decimal("0.00"))
        self.assertEqual(Decimal(data["monto_liquidar"]), Decimal("500.00"))

    def test_tasa_comision_uno_calcula_todo_como_comision(self):
        self._crear_pedido_entregado(total=Decimal("500.00"), creado_en=_aware(2026, 7, 21))

        with patch("rassa.blueprints.liquidaciones.views.COMISION_RASSA", new=Decimal("1.00")):
            resp = self.client.post(
                "/api/liquidaciones/calcular/",
                {
                    "agricultor": self.usuario_agricultor.id_usuario,
                    "semana": 30,
                    "anio": 2026,
                },
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()["data"]
        self.assertEqual(Decimal(data["monto_ventas"]), Decimal("500.00"))
        self.assertEqual(Decimal(data["comision"]), Decimal("500.00"))
        self.assertEqual(Decimal(data["monto_liquidar"]), Decimal("0.00"))

    def test_default_tasa_comision_es_10_por_ciento(self):
        self._crear_pedido_entregado(total=Decimal("1000.00"), creado_en=_aware(2026, 7, 21))

        # Sin enviar tasa_comision → debe aplicar 10% por defecto
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()["data"]
        self.assertEqual(Decimal(data["comision"]), Decimal("100.00"))
        self.assertEqual(Decimal(data["monto_liquidar"]), Decimal("900.00"))

    def test_409_incluye_id_liquidacion_existente(self):
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))

        resp1 = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        first_id = resp1.json()["data"]["id_liquidacion"]

        resp2 = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        self.assertEqual(resp2.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp2.json()["data"]["id_liquidacion_existente"], first_id)

    def test_semana_invalida_para_anio_retorna_400(self):
        # 2027 no tiene semana 53 (53 solo aparece en años que empiecen en jueves
        # o cuando el año bisiesto termina en jueves — 2027 no aplica)
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 53,
                "anio": 2027,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("no existe", str(resp.json()))

    def test_tasa_comision_en_request_es_ignorada(self):
        """tasa_comision enviada en el request es ignorada y se usa la tasa del server."""
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))

        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
                "tasa_comision": "0.5000",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()["data"]
        self.assertEqual(Decimal(data["comision"]), Decimal("10.00"))

    def test_calcular_sin_estado_entregado_en_bd_retorna_500(self):
        """Si el seed no ha creado el EstadoPedido 'entregado', calcular
        retorna 500 con mensaje claro (revisión 4R R4 SUGGESTION)."""
        from unittest.mock import patch

        from rassa.models import EstadoPedido

        # Forzar que el .get() de EstadoPedido lance DoesNotExist
        with patch("rassa.blueprints.liquidaciones.views.EstadoPedido.objects.get") as mock_get:
            mock_get.side_effect = EstadoPedido.DoesNotExist("entregado")
            resp = self.client.post(
                "/api/liquidaciones/calcular/",
                {
                    "agricultor": self.usuario_agricultor.id_usuario,
                    "semana": 30,
                    "anio": 2026,
                },
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("estado 'entregado'", resp.json()["message"])

    def test_calcular_con_parcial_existente_retorna_409(self):
        """Una liquidación en estado 'parcial' (reservado para futuro)
        también cuenta como duplicada para re-calcular (revisión 4R R3
        advertencia sobre 'solo se testea pendiente')."""
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))

        # Crear liquidación y forzar estado 'parcial' manualmente
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        liquidacion_id = resp.json()["data"]["id_liquidacion"]
        Liquidacion.objects.filter(pk=liquidacion_id).update(estado="parcial")

        # Re-calcular el mismo periodo con parcial existente → 409
        resp2 = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        self.assertEqual(resp2.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            resp2.json()["data"]["id_liquidacion_existente"],
            liquidacion_id,
        )


class MarcarPagadaEdgeCasesTest(LiquidacionesTestBase):
    """Casos borde de marcar como pagada (transición desde parcial)."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user_admin)
        self._crear_pedido_entregado(total=Decimal("500.00"), creado_en=_aware(2026, 7, 21))

        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        self.liquidacion_id = resp.json()["data"]["id_liquidacion"]

    def test_marcar_pagada_sobre_parcial_es_valido(self):
        # Forzar estado "parcial" manualmente (no hay UI que lo cree aún)
        Liquidacion.objects.filter(pk=self.liquidacion_id).update(estado="parcial")

        resp = self.client.post(
            f"/api/liquidaciones/{self.liquidacion_id}/marcar-pagada/",
            {"tipo_pago": self.tipo_efectivo.id_tipo_pago},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["data"]["estado"], "pagada")

    def test_no_se_puede_recalcular_despues_de_pagada(self):
        """Una liquidación `pagada` es terminal: re-calcular el mismo
        periodo retorna 409 con el id de la existente.

        Cierra el riesgo de doble pago (revisión 4R R1).
        """
        # Marcar pagada la existente
        self.client.post(
            f"/api/liquidaciones/{self.liquidacion_id}/marcar-pagada/",
            {"tipo_pago": self.tipo_efectivo.id_tipo_pago},
            format="json",
        )
        self.assertEqual(Liquidacion.objects.get(pk=self.liquidacion_id).estado, "pagada")

        # Re-calcular el mismo periodo
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            resp.json()["data"]["id_liquidacion_existente"],
            self.liquidacion_id,
        )
        # Sigue habiendo solo 1 liquidación
        self.assertEqual(
            Liquidacion.objects.filter(
                fk_agricultor=self.usuario_agricultor,
                periodo_inicio=date(2026, 7, 20),
                periodo_fin=date(2026, 7, 26),
            ).count(),
            1,
        )


class LiquidacionFiltrosTest(LiquidacionesTestBase):
    """Filtros adicionales: periodo_inicio, periodo_fin, valores inválidos."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user_admin)

    def test_filtro_por_periodo_inicio_y_fin(self):
        # Liquidación en semana 30 de 2026 (lunes 2026-07-20 a domingo 2026-07-26)
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))
        self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )

        # Rango que incluye 2026-07-20 → debe incluirla
        resp = self.client.get("/api/liquidaciones/?periodo_inicio=2026-01-01&periodo_fin=2026-12-31")
        self.assertEqual(len(resp.json()["data"]["results"]), 1)

        # Rango que NO incluye 2026-07-20 → no debe incluirla
        resp_empty = self.client.get("/api/liquidaciones/?periodo_inicio=2027-01-01&periodo_fin=2027-12-31")
        self.assertEqual(len(resp_empty.json()["data"]["results"]), 0)

    def test_filtro_estado_invalido_retorna_lista_vacia(self):
        # No debe explotar; solo devolver lista vacía
        resp = self.client.get("/api/liquidaciones/?estado=estado_inexistente")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()["data"]["results"]), 0)

    def test_filtro_agricultor_inexistente_retorna_lista_vacia(self):
        resp = self.client.get("/api/liquidaciones/?agricultor=999999")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()["data"]["results"]), 0)


class LiquidacionPaginationTest(LiquidacionesTestBase):
    """Paginación: el endpoint usa CatalogPagination (page_size=20)."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user_admin)

    def test_paginacion_retorna_envelope_con_results(self):
        # Crear 3 liquidaciones (semanas distintas)
        fechas_por_semana = {
            28: _aware(2026, 7, 6),
            29: _aware(2026, 7, 13),
            30: _aware(2026, 7, 21),
        }
        for semana, fecha in fechas_por_semana.items():
            self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=fecha)
            self.client.post(
                "/api/liquidaciones/calcular/",
                {
                    "agricultor": self.usuario_agricultor.id_usuario,
                    "semana": semana,
                    "anio": 2026,
                },
                format="json",
            )

        resp = self.client.get("/api/liquidaciones/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()["data"]
        self.assertIn("results", data)
        self.assertIn("count", data)
        self.assertEqual(data["count"], 3)
        self.assertEqual(len(data["results"]), 3)

    def test_paginacion_con_mas_de_20_items_retorna_count_y_next(self):
        """CatalogPagination tiene page_size=20. Con >20 items debe
        devolver count exacto y URL de next page (revisión 4R R3)."""
        # 22 liquidaciones en 22 semanas distintas de 2026.
        # Usamos miércoles (weekday 3) de cada semana para asegurar que
        # la fecha cae en la semana ISO correcta (algunas semanas ISO
        # cruzan año, e.g. semana 1 de 2026 arranca el 2025-12-29).
        for semana in range(1, 23):
            fecha_miercoles = date.fromisocalendar(2026, semana, 3)
            self._crear_pedido_entregado(
                total=Decimal("100.00"),
                creado_en=_aware(fecha_miercoles.year, fecha_miercoles.month, fecha_miercoles.day),
            )
            self.client.post(
                "/api/liquidaciones/calcular/",
                {
                    "agricultor": self.usuario_agricultor.id_usuario,
                    "semana": semana,
                    "anio": 2026,
                },
                format="json",
            )

        resp = self.client.get("/api/liquidaciones/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()["data"]
        self.assertEqual(data["count"], 22)
        self.assertEqual(len(data["results"]), 20)
        self.assertIsNotNone(data["next"])
        # Página 2 tiene los 2 restantes
        resp2 = self.client.get("/api/liquidaciones/?page=2")
        self.assertEqual(len(resp2.json()["data"]["results"]), 2)


class CalcularYearBoundaryTest(LiquidacionesTestBase):
    """Bordes de año: la ISO week 53 de 2026 cruza al 2027 (28 dic → 3 ene)."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user_admin)

    def test_semana_53_de_2026_cruza_anio_nuevo(self):
        # 2026 tiene 53 semanas ISO. La semana 53 va del 2026-12-28 al 2027-01-03.
        self._crear_pedido_entregado(
            total=Decimal("100.00"),
            creado_en=_aware(2026, 12, 28),
        )
        # Sanity: pedido del domingo previo pertenece a la semana 52 de 2026,
        # NO debe contar para semana 53.
        self._crear_pedido_entregado(
            total=Decimal("999.00"),
            creado_en=_aware(2026, 12, 27),
        )
        # Borde lejano: pedido del domingo 2027-01-03 a última hora debe ser incluido en semana 53 (revisión 4R R3).
        self._crear_pedido_entregado(
            total=Decimal("50.00"),
            creado_en=_aware(2027, 1, 3, hour=23, minute=59),
        )

        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 53,
                "anio": 2026,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.json())
        data = resp.json()["data"]
        self.assertEqual(data["periodo_inicio"], "2026-12-28")
        self.assertEqual(data["periodo_fin"], "2027-01-03")
        # Cuenta el del 28 (100.00) y el del 3 (50.00), total = 150.00
        self.assertEqual(Decimal(data["monto_ventas"]), Decimal("150.00"))
        self.assertEqual(len(data["ventas"]), 2)

    def test_semana_53_de_2026_excluye_lunes_2027_01_04(self):
        """El lunes 2027-01-04 pertenece a la SEMANA 1 de 2027, no a la
        semana 53 de 2026. El filtro del view usa `<` exclusivo sobre el
        lunes siguiente, por lo que el 04 NO cuenta (revisión 4R R3
        SUGGESTION — borde lejano del año)."""
        self._crear_pedido_entregado(
            total=Decimal("100.00"),
            creado_en=_aware(2027, 1, 4, hour=10),  # lunes de la semana 1 de 2027
        )
        # El lunes previo 2026-12-28 sí cuenta
        self._crear_pedido_entregado(
            total=Decimal("200.00"),
            creado_en=_aware(2026, 12, 28),
        )

        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 53,
                "anio": 2026,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.json())
        data = resp.json()["data"]
        # Solo cuenta el 2026-12-28, NO el 2027-01-04 (que es semana 1 de 2027)
        self.assertEqual(Decimal(data["monto_ventas"]), Decimal("200.00"))
        self.assertEqual(len(data["ventas"]), 1)
        self.assertEqual(
            data["ventas"][0]["creado_en"][:10],  # YYYY-MM-DD
            "2026-12-28",
        )


class CalcularConcurrencyTest(TransactionTestCase):
    """Concurrencia en `calcular`: 4 layers de anti-duplicado deben
    garantizar que solo 1 request cree la liquidación; el resto recibe 409.

    Hereda SOLO de TransactionTestCase (no de LiquidacionesTestBase) porque
    APITestCase abre un atomic block que oculta los datos a los worker threads.
    """

    def setUp(self):
        # Inicializa los datos vía la base (no el setUp de APITestCase,
        # porque TransactionTestCase no lo invoca).
        self.rol_admin = Rol.objects.create(nombre_rol="Admin", descripcion="Admin")
        self.rol_agricultor = Rol.objects.create(nombre_rol="Agricultor", descripcion="Agricultor")
        self.estado_entregado = EstadoPedido.objects.create(tipo_estado="entregado", descripcion="Entregado")
        self.tipo_efectivo = TipoPago.objects.create(nombre="Efectivo")

        persona_admin = Persona.objects.create(
            nombre="Admin",
            apellido_paterno="Conc",
            fecha_nacimiento="1990-01-01",
            sexo="M",
            domicilio="Calle 1",
        )
        user_admin = User.objects.create_user(username="admin@conc.test", email="admin@conc.test", password="pass123")
        self.user_admin = user_admin
        Usuario.objects.create(
            fk_user=user_admin,
            fk_persona=persona_admin,
            telefono="111",
            correo="admin@conc.test",
            fk_rol=self.rol_admin,
        )

        persona_agricultor = Persona.objects.create(
            nombre="Agri",
            apellido_paterno="Conc",
            fecha_nacimiento="1985-01-01",
            sexo="M",
            domicilio="Rancho 1",
        )
        user_agricultor = User.objects.create_user(
            username="agri@conc.test", email="agri@conc.test", password="pass123"
        )
        self.usuario_agricultor = Usuario.objects.create(
            fk_user=user_agricultor,
            fk_persona=persona_agricultor,
            telefono="222",
            correo="agri@conc.test",
            fk_rol=self.rol_agricultor,
        )

        categoria = CategoriaProducto.objects.create(nombre="Verduras", descripcion="x")
        unidad = Unidad.objects.create(tipo="peso", nombre="Kilogramo", abreviatura="kg")
        producto = Producto.objects.create(
            nombre_producto="Tomate",
            descripcion="x",
            fk_categoria=categoria,
            fk_unidad=unidad,
            precio=Decimal("25.00"),
            stock=1000,
        )
        publicacion = PublicacionSemanal.objects.create(
            fk_agricultor=self.usuario_agricultor,
            fecha_publicacion=date(2026, 7, 20),
            semana=30,
            estado="publicado",
        )
        producto_semanal = ProductoSemanal.objects.create(
            fk_publicacion=publicacion,
            fk_producto=producto,
            fk_unidad=unidad,
            precio=Decimal("25.00"),
            stock=500,
        )

        # 1 pedido entregado del agricultor (fk_cliente debe ser Usuario)
        pedido = PedidoCabecera.objects.create(
            fk_cliente=user_admin.usuario,
            fk_estado=self.estado_entregado,
            subtotal=Decimal("100.00"),
            iva=Decimal("0.00"),
            total=Decimal("100.00"),
        )
        PedidoCabecera.objects.filter(pk=pedido.pk).update(creado_en=_aware(2026, 7, 21))
        DetallePedido.objects.create(
            fk_pedido=pedido,
            fk_producto_semanal=producto_semanal,
            nombre_producto="Tomate",
            precio_unitario=Decimal("25.00"),
            cantidad=4,
            importe=Decimal("100.00"),
        )

    @unittest.skipUnless(
        connection.vendor == "postgresql",
        "El test depende del comportamiento real de select_for_update en PostgreSQL "
        "(advisory locks de Pago.save, sqlstate 40P01). En SQLite las locks son no-op.",
    )
    def test_calcular_bajo_concurrencia_solo_una_se_crea(self):
        NUM_THREADS = 5
        results: list[tuple[int, dict]] = []
        barrier = threading.Barrier(NUM_THREADS)

        def calcular():
            client = APIClient()
            client.force_authenticate(user=self.user_admin)
            barrier.wait()
            resp = client.post(
                "/api/liquidaciones/calcular/",
                {
                    "agricultor": self.usuario_agricultor.id_usuario,
                    "semana": 30,
                    "anio": 2026,
                },
                format="json",
            )
            results.append((resp.status_code, resp.json()))

        threads = [threading.Thread(target=calcular) for _ in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), NUM_THREADS)
        # Ningún 500 (deadlock u otros errores de BD están manejados)
        codes = [r[0] for r in results]
        self.assertNotIn(status.HTTP_500_INTERNAL_SERVER_ERROR, codes)
        # Exactamente 1 creó (201) y el resto recibió 409
        self.assertEqual(
            sum(1 for c in codes if c == status.HTTP_201_CREATED),
            1,
            f"Esperaba 1 created, recibí {results}",
        )
        self.assertEqual(
            sum(1 for c in codes if c in (status.HTTP_409_CONFLICT, status.HTTP_400_BAD_REQUEST)),
            NUM_THREADS - 1,
            f"Esperaba {NUM_THREADS - 1} no-ops (409 o 400), recibí {results}",
        )
        # Y en la BD solo debe haber 1 liquidación
        self.assertEqual(
            Liquidacion.objects.filter(
                fk_agricultor=self.usuario_agricultor,
                periodo_inicio=date(2026, 7, 20),
                periodo_fin=date(2026, 7, 26),
            ).count(),
            1,
        )

    @unittest.skipUnless(
        connection.vendor == "postgresql",
        "El test depende del comportamiento real de select_for_update en PostgreSQL.",
    )
    def test_calcular_bajo_concurrencia_con_pedidos_disjuntos(self):
        """Prueba de concurrencia para la creación de liquidaciones.
        Dado que ambos threads operan sobre el mismo agricultor y periodo,
        el view recuperará y bloqueará el mismo conjunto de pedidos.
        Este test valida que el constraint de base de datos actúe como
        salvaguarda definitiva ante cualquier intento de duplicación concurrente.
        """
        NUM_THREADS = 5

        # Crear NUM_THREADS pedidos disjuntos del mismo agricultor
        from rassa.models import DetallePedido, PublicacionSemanal

        pedidos = []
        publicacion = PublicacionSemanal.objects.first()
        ps = publicacion.productosemanal_set.first()
        for _ in range(NUM_THREADS):
            p = PedidoCabecera.objects.create(
                fk_cliente=self.user_admin.usuario,
                fk_estado=self.estado_entregado,
                subtotal=Decimal("100.00"),
                iva=Decimal("0.00"),
                total=Decimal("100.00"),
            )
            PedidoCabecera.objects.filter(pk=p.pk).update(creado_en=_aware(2026, 7, 21))
            DetallePedido.objects.create(
                fk_pedido=p,
                fk_producto_semanal=ps,
                nombre_producto="Tomate",
                precio_unitario=Decimal("25.00"),
                cantidad=4,
                importe=Decimal("100.00"),
            )
            pedidos.append(p)

        results: list[tuple[int, dict]] = []
        barrier = threading.Barrier(NUM_THREADS)

        def calcular():
            client = APIClient()
            client.force_authenticate(user=self.user_admin)
            barrier.wait()
            resp = client.post(
                "/api/liquidaciones/calcular/",
                {
                    "agricultor": self.usuario_agricultor.id_usuario,
                    "semana": 30,
                    "anio": 2026,
                },
                format="json",
            )
            results.append((resp.status_code, resp.json()))

        threads = [threading.Thread(target=calcular) for _ in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), NUM_THREADS)
        codes = [r[0] for r in results]
        self.assertNotIn(status.HTTP_500_INTERNAL_SERVER_ERROR, codes)
        # Dado que todos los threads operan sobre la misma semana del agricultor,
        # el bloqueo select_for_update sobre los pedidos y la restricción de unicidad
        # evitan la creación de liquidaciones duplicadas.
        successes = sum(1 for c in codes if c == status.HTTP_201_CREATED)
        duplicates = sum(1 for c in codes if c in (status.HTTP_409_CONFLICT, status.HTTP_400_BAD_REQUEST))
        self.assertEqual(
            successes + duplicates,
            NUM_THREADS,
            f"Esperaba solo 201+409/400, recibí {codes}",
        )
        self.assertGreater(
            duplicates,
            0,
            "Se esperaba que las peticiones concurrentes fueran serializadas/bloqueadas por el view.",
        )
        # En la BD: solo 1 liquidación activa
        self.assertEqual(
            Liquidacion.objects.filter(
                fk_agricultor=self.usuario_agricultor,
                periodo_inicio=date(2026, 7, 20),
                periodo_fin=date(2026, 7, 26),
            ).count(),
            1,
        )

    @unittest.skipUnless(
        connection.vendor == "postgresql",
        "El test depende del comportamiento real de select_for_update en PostgreSQL.",
    )
    def test_marcar_pagada_bajo_concurrencia_solo_un_pago_se_crea(self):
        """Si múltiples hilos intentan marcar como pagada la misma liquidación simultáneamente,
        solo se crea 1 pago y el estado cambia a pagada sin errores 500."""
        client_admin = APIClient()
        client_admin.force_authenticate(user=self.user_admin)
        resp_calc = client_admin.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        self.assertEqual(resp_calc.status_code, status.HTTP_201_CREATED)
        liquidacion_id = resp_calc.json()["data"]["id_liquidacion"]

        NUM_THREADS = 5
        results: list[tuple[int, dict]] = []
        barrier = threading.Barrier(NUM_THREADS)

        def pagar():
            c = APIClient()
            c.force_authenticate(user=self.user_admin)
            barrier.wait()
            resp = c.post(
                f"/api/liquidaciones/{liquidacion_id}/marcar-pagada/",
                {"tipo_pago": self.tipo_efectivo.id_tipo_pago, "referencia": "REF-CONC"},
                format="json",
            )
            results.append((resp.status_code, resp.json()))

        threads = [threading.Thread(target=pagar) for _ in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), NUM_THREADS)
        codes = [r[0] for r in results]
        self.assertNotIn(status.HTTP_500_INTERNAL_SERVER_ERROR, codes)

        liq = Liquidacion.objects.get(pk=liquidacion_id)
        self.assertEqual(liq.estado, "pagada")
        self.assertIsNotNone(liq.fk_pago_liquidacion)
        # R3 WARNING: Verificar que exactamente 1 objeto Pago fue creado en BD para esta liquidacion
        self.assertEqual(Pago.objects.filter(liquidacion=liq).count(), 1)


class MarcarPagadaMockedTest(LiquidacionesTestBase):
    """Tests de resilience con mocks para errores de BD en Pago.save
    (revisión 4R R3 R4 SUGGESTIONS sobre casos de error no cubiertos)."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user_admin)
        self._crear_pedido_entregado(total=Decimal("500.00"), creado_en=_aware(2026, 7, 21))
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        self.liquidacion_id = resp.json()["data"]["id_liquidacion"]

    def test_marcar_pagada_pago_save_falla_con_500(self):
        """Si Pago.save() lanza un DatabaseError no-deadlock, el view
        retorna 500 con mensaje claro (no 409 deadlock ni 200 falso)."""
        with patch("rassa.blueprints.liquidaciones.views.Pago.save") as mock_save:
            mock_save.side_effect = OperationalError("connection lost")
            resp = self.client.post(
                f"/api/liquidaciones/{self.liquidacion_id}/marcar-pagada/",
                {"tipo_pago": self.tipo_efectivo.id_tipo_pago},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("procesar el pago", resp.json()["message"])

    def test_marcar_pagada_deadlock_en_pago_save_retorna_409(self):
        """Si Pago.save() lanza un deadlock PostgreSQL (sqlstate 40P01),
        el view lo detecta y retorna 409 con mensaje de reintento."""
        # Construir un OperationalError con sqlstate=40P01. El
        # __cause__ debe ser BaseException; usamos una excepción real.
        cause = OperationalError("underlying")
        cause.sqlstate = "40P01"
        err = OperationalError("deadlock detected")
        err.__cause__ = cause

        with patch("rassa.blueprints.liquidaciones.views.Pago.save") as mock_save:
            mock_save.side_effect = err
            resp = self.client.post(
                f"/api/liquidaciones/{self.liquidacion_id}/marcar-pagada/",
                {"tipo_pago": self.tipo_efectivo.id_tipo_pago},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("Reintente", resp.json()["message"])


class LiquidacionAdditionalEdgeCasesTest(LiquidacionesTestBase):
    """Casos borde adicionales (revisión 4R R3)."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user_admin)

    def test_retrieve_404_si_no_existe(self):
        resp = self.client.get("/api/liquidaciones/99999/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_calcular_agricultor_inactivo_via_view_retorna_400(self):
        """Si el serializer no bloquea al agricultor inactivo (defensa en
        profundidad en el view), el view debe hacerlo."""
        self.usuario_agricultor.estado = False
        self.usuario_agricultor.save()
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_calcular_semana_cero_retorna_400(self):
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 0,
                "anio": 2026,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_calcular_anio_fuera_de_rango_retorna_400(self):
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 1999,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2101,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_marcar_pagada_referencia_muy_larga_retorna_400(self):
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        liquidacion_id = resp.json()["data"]["id_liquidacion"]

        # referencia de 101 caracteres (max_length=100)
        resp = self.client.post(
            f"/api/liquidaciones/{liquidacion_id}/marcar-pagada/",
            {
                "tipo_pago": self.tipo_efectivo.id_tipo_pago,
                "referencia": "X" * 101,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_query_param_agricultor_invalido_retorna_400(self):
        resp = self.client.get("/api/liquidaciones/?agricultor=abc")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_query_param_periodo_invalido_retorna_400(self):
        resp = self.client.get("/api/liquidaciones/?periodo_inicio=basura")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_detalle_usa_snapshot_inmutable(self):
        """Crea liquidación, luego cambia el estado del pedido. El detalle
        debe seguir mostrando el pedido (snapshot), no el estado en vivo."""
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        liquidacion_id = resp.json()["data"]["id_liquidacion"]

        # Cambiar el estado del pedido fuera de la liquidación
        from rassa.models import PedidoCabecera

        pedido = PedidoCabecera.objects.get(creado_en__date=date(2026, 7, 21))
        pedido.fk_estado = self.estado_listo
        pedido.save()

        # El detalle sigue mostrando el pedido en sus ventas (snapshot)
        resp = self.client.get(f"/api/liquidaciones/{liquidacion_id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()["data"]["ventas"]), 1)

    def test_marcar_pagada_idempotencia(self):
        """Si marcar_pagada recibe una liquidación ya pagada, devuelve 200 OK
        con el detalle y el folio del pago en lugar de un error 400 (revisión 4R R4)."""
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))

        # Calcular
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        liquidacion_id = resp.json()["data"]["id_liquidacion"]

        # Marcar pagada (primer intento)
        resp1 = self.client.post(
            f"/api/liquidaciones/{liquidacion_id}/marcar-pagada/",
            {"tipo_pago": self.tipo_efectivo.id_tipo_pago},
            format="json",
        )
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        folio_original = resp1.json()["data"]["pago_liquidacion"]["folio"]

        # Marcar pagada (segundo intento)
        resp2 = self.client.post(
            f"/api/liquidaciones/{liquidacion_id}/marcar-pagada/",
            {"tipo_pago": self.tipo_efectivo.id_tipo_pago},
            format="json",
        )
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertIn("ya está marcada como pagada", resp2.json()["message"])
        self.assertEqual(resp2.json()["data"]["pago_liquidacion"]["folio"], folio_original)

    def test_marcar_pagada_discrepancia_parametros_retorna_409(self):
        """Si se intenta marcar como pagada una liquidación ya pagada enviando un tipo_pago o referencia
        distinto, la API debe rechazar la discrepancia con 409 Conflict (revisión 4R SUGGESTION)."""
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))

        # Calcular
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        liquidacion_id = resp.json()["data"]["id_liquidacion"]

        # Marcar pagada (con efectivo)
        resp1 = self.client.post(
            f"/api/liquidaciones/{liquidacion_id}/marcar-pagada/",
            {"tipo_pago": self.tipo_efectivo.id_tipo_pago, "referencia": "REF-1"},
            format="json",
        )
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)

        # Re-intentar con datos discrepantes (con transferencia) -> 409 Conflict
        resp2 = self.client.post(
            f"/api/liquidaciones/{liquidacion_id}/marcar-pagada/",
            {"tipo_pago": self.tipo_transferencia.id_tipo_pago, "referencia": "REF-2"},
            format="json",
        )
        self.assertEqual(resp2.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("datos distintos", resp2.json()["message"])

    def test_calcular_excluye_pedidos_ya_liquidados(self):
        """Pedidos ya vinculados en una liquidación activa no deben ser incluidos
        en un nuevo cálculo (prevención de doble pago / revisión 4R R1)."""
        # Crear 2 pedidos entregados en semana 30
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))
        self._crear_pedido_entregado(total=Decimal("50.00"), creado_en=_aware(2026, 7, 22))

        # Crear una liquidación dummy en un periodo diferente (semana 29)
        from rassa.models import Liquidacion, LiquidacionVenta, PedidoCabecera

        liq_dummy = Liquidacion.objects.create(
            fk_agricultor=self.usuario_agricultor,
            periodo_inicio=date(2026, 7, 13),
            periodo_fin=date(2026, 7, 19),
            monto_ventas=Decimal("100.00"),
            comision=Decimal("10.00"),
            monto_liquidar=Decimal("90.00"),
            estado="pagada",
        )
        # Vincular el primer pedido (100.00) de la semana 30 a esta liquidación dummy
        LiquidacionVenta.objects.create(
            fk_liquidacion=liq_dummy,
            fk_pedido=PedidoCabecera.objects.get(total=Decimal("100.00")),
            monto_aportado=Decimal("100.00"),
        )

        # Ahora calculamos la semana 30
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.json())
        data = resp.json()["data"]
        # Debe excluir el pedido de 100.00 (ya liquidado) y solo incluir el de 50.00
        self.assertEqual(Decimal(data["monto_ventas"]), Decimal("50.00"))
        self.assertEqual(len(data["ventas"]), 1)

    def test_detalle_usa_monto_aportado_snapshot_cuando_cambia_pedido_total(self):
        """Si el total del pedido cambia después de liquidarse, el detalle de la liquidación
        debe seguir reportando el monto_aportado del snapshot, no el total en vivo."""
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))
        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
            },
            format="json",
        )
        liquidacion_id = resp.json()["data"]["id_liquidacion"]

        # Modificar el total en vivo del pedido
        from rassa.models import PedidoCabecera

        pedido = PedidoCabecera.objects.get(creado_en__date=date(2026, 7, 21))
        pedido.total = Decimal("500.00")
        pedido.save()

        # El detalle debe seguir reportando 100.00
        resp = self.client.get(f"/api/liquidaciones/{liquidacion_id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(resp.json()["data"]["ventas"][0]["total"]), Decimal("100.00"))

    def test_calcular_pedido_multi_agricultor_solo_suma_lineas_propias(self):
        """Si un pedido contiene productos de múltiples agricultores, calcular solo
        debe sumar las líneas correspondientes al agricultor a liquidar."""
        from django.contrib.auth.models import User

        from rassa.models import DetallePedido, Persona, ProductoSemanal, PublicacionSemanal, Usuario

        # Crear segundo agricultor
        p2 = Persona.objects.create(
            nombre="Segundo",
            apellido_paterno="Agri",
            fecha_nacimiento="1990-01-01",
            sexo="M",
            domicilio="Rancho 3",
        )
        u2 = User.objects.create_user(username="agri2@test.com", email="agri2@test.com", password="pass")
        agri2 = Usuario.objects.create(
            fk_user=u2,
            fk_persona=p2,
            telefono="999",
            correo="agri2@test.com",
            fk_rol=self.rol_agricultor,
        )
        pub2 = PublicacionSemanal.objects.create(
            fk_agricultor=agri2,
            fecha_publicacion=date(2026, 7, 20),
            semana=30,
            estado="publicado",
        )
        ps2 = ProductoSemanal.objects.create(
            fk_publicacion=pub2,
            fk_producto=self.producto,
            fk_unidad=self.unidad,
            precio=Decimal("50.00"),
            stock=100,
        )

        # Pedido con líneas de ambos
        pedido = PedidoCabecera.objects.create(
            fk_cliente=self.usuario_cliente,
            fk_estado=self.estado_entregado,
            fk_vendedor=self.usuario_vendedor,
            subtotal=Decimal("300.00"),
            iva=Decimal("0.00"),
            total=Decimal("300.00"),
        )
        PedidoCabecera.objects.filter(pk=pedido.pk).update(creado_en=_aware(2026, 7, 21))

        # Línea de agricultor 1 (monto 100.00)
        DetallePedido.objects.create(
            fk_pedido=pedido,
            fk_producto_semanal=self.producto_semanal,
            nombre_producto="Papa",
            precio_unitario=Decimal("25.00"),
            cantidad=4,
            importe=Decimal("100.00"),
        )
        # Línea de agricultor 2 (monto 200.00)
        DetallePedido.objects.create(
            fk_pedido=pedido,
            fk_producto_semanal=ps2,
            nombre_producto="Tomate",
            precio_unitario=Decimal("50.00"),
            cantidad=4,
            importe=Decimal("200.00"),
        )

        # Calcular para agricultor 1
        resp = self._calcular(agricultor_id=self.usuario_agricultor.id_usuario, semana=30, anio=2026)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()["data"]
        # Debe ser exactamente 100.00 (no 300.00)
        self.assertEqual(Decimal(data["monto_ventas"]), Decimal("100.00"))
        self.assertEqual(Decimal(data["ventas"][0]["total"]), Decimal("100.00"))

        # C1 Fix Test: El 2º agricultor puede liquidar su parte del mismo pedido compartido después del 1º
        resp2 = self._calcular(agricultor_id=agri2.id_usuario, semana=30, anio=2026)
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED)
        data2 = resp2.json()["data"]
        self.assertEqual(Decimal(data2["monto_ventas"]), Decimal("200.00"))
        self.assertEqual(Decimal(data2["ventas"][0]["total"]), Decimal("200.00"))

    def test_retrieve_con_id_no_numerico_retorna_400(self):
        """C3 Fix Test: GET /api/liquidaciones/abc/ retorna 400 Bad Request en lugar de 500."""
        self.client.force_authenticate(user=self.user_admin)
        resp = self.client.get("/api/liquidaciones/abc/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_marcar_pagada_con_pk_no_numerico_retorna_400(self):
        """C5/C3 Fix Test: POST /api/liquidaciones/abc/marcar-pagada/ retorna 400 Bad Request."""
        from rassa.models import TipoPago

        tipo_pago = TipoPago.objects.first()
        self.client.force_authenticate(user=self.user_admin)
        resp = self.client.post("/api/liquidaciones/abc/marcar-pagada/", {"tipo_pago": tipo_pago.pk})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_marcar_pagada_con_pago_existente_previene_doble_pago(self):
        """C5/C8 Fix Test: si la liquidacion ya tiene un Pago asignado, previene crear un segundo Pago."""
        from rassa.models import TipoPago

        tipo_pago = TipoPago.objects.first()
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))
        resp = self._calcular(semana=30, anio=2026)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        liq_id = resp.json()["data"]["id_liquidacion"]

        # Marcar pagada por primera vez
        resp_pago1 = self.client.post(
            f"/api/liquidaciones/{liq_id}/marcar-pagada/",
            {"tipo_pago": tipo_pago.pk, "referencia": "REF123"},
        )
        self.assertEqual(resp_pago1.status_code, status.HTTP_200_OK)
        conteo_pagos = Pago.objects.count()

        # Re-enviar la misma petición de pago
        resp_pago2 = self.client.post(
            f"/api/liquidaciones/{liq_id}/marcar-pagada/",
            {"tipo_pago": tipo_pago.pk, "referencia": "REF123"},
        )
        self.assertEqual(resp_pago2.status_code, status.HTTP_200_OK)
        # El conteo total de objetos Pago no debe incrementarse
        self.assertEqual(Pago.objects.count(), conteo_pagos)

    def test_redondeo_half_up_comision_fraccionaria(self):
        """Verifica la regla ROUND_HALF_UP con centavos fraccionarios.

        100.45 * 10% = 10.045 -> 10.05 comision, 90.40 monto liquidar.
        """
        self._crear_pedido_entregado(total=Decimal("100.45"), creado_en=_aware(2026, 7, 21))
        resp = self._calcular(semana=30, anio=2026)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()["data"]
        self.assertEqual(Decimal(data["monto_ventas"]), Decimal("100.45"))
        self.assertEqual(Decimal(data["comision"]), Decimal("10.05"))
        self.assertEqual(Decimal(data["monto_liquidar"]), Decimal("90.40"))
