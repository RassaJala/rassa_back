"""Pruebas para el módulo de Liquidaciones."""

import threading
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.models import User
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


class CalcularLiquidacionTest(LiquidacionesTestBase):
    """Cálculo de liquidaciones semanales por agricultor."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user_admin)

    def test_calcular_con_tres_ventas_calcula_total_y_comision(self):
        self._crear_pedido_entregado(total=Decimal("100.00"), creado_en=_aware(2026, 7, 21))
        self._crear_pedido_entregado(total=Decimal("200.00"), creado_en=_aware(2026, 7, 23))
        self._crear_pedido_entregado(total=Decimal("300.00"), creado_en=_aware(2026, 7, 26, hour=10))

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
        self.assertEqual(Decimal(data["monto_ventas"]), Decimal("100.00"))

    def test_calcular_con_tasa_personalizada(self):
        self._crear_pedido_entregado(total=Decimal("1000.00"), creado_en=_aware(2026, 7, 21))

        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
                "tasa_comision": "0.0500",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()["data"]
        self.assertEqual(Decimal(data["monto_ventas"]), Decimal("1000.00"))
        self.assertEqual(Decimal(data["comision"]), Decimal("50.00"))
        self.assertEqual(Decimal(data["monto_liquidar"]), Decimal("950.00"))

    def test_calcular_bloquea_duplicado_409(self):
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
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)

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

    def test_marcar_pagada_sobre_ya_pagada_retorna_400(self):
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
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)

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

    def test_retrieve_rechaza_no_admin_con_403(self):
        # Crear una liquidación con admin
        resp = self._calcular()
        liquidacion_id = resp.json()["data"]["id_liquidacion"]

        # Vendedor no debe poder ver el detalle
        self.client.force_authenticate(user=self.user_vendedor)
        resp_get = self.client.get(f"/api/liquidaciones/{liquidacion_id}/")
        self.assertEqual(resp_get.status_code, status.HTTP_403_FORBIDDEN)


class CalcularEdgeCasesTest(LiquidacionesTestBase):
    """Casos borde de cálculo (tasa 0/1, default, semana inválida, 409 con id)."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user_admin)

    def test_tasa_comision_cero_calcula_sin_comision(self):
        self._crear_pedido_entregado(total=Decimal("500.00"), creado_en=_aware(2026, 7, 21))

        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
                "tasa_comision": "0.0000",
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

        resp = self.client.post(
            "/api/liquidaciones/calcular/",
            {
                "agricultor": self.usuario_agricultor.id_usuario,
                "semana": 30,
                "anio": 2026,
                "tasa_comision": "1.0000",
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

    def test_re_calcular_despues_de_pagada_es_valido(self):
        """Si la liquidación previa está 'pagada', se puede crear una nueva
        para el mismo (agricultor, periodo). Coincide con el constraint de BD."""
        # Marcar pagada la existente
        self.client.post(
            f"/api/liquidaciones/{self.liquidacion_id}/marcar-pagada/",
            {"tipo_pago": self.tipo_efectivo.id_tipo_pago},
            format="json",
        )
        self.assertEqual(Liquidacion.objects.get(pk=self.liquidacion_id).estado, "pagada")

        # Re-calcular para el mismo periodo
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
        new_id = resp.json()["data"]["id_liquidacion"]
        self.assertNotEqual(new_id, self.liquidacion_id, "Debe ser una liquidación nueva")
        self.assertEqual(resp.json()["data"]["estado"], "pendiente")
        # Ahora hay 2 liquidaciones: la pagada y la nueva pendiente
        self.assertEqual(
            Liquidacion.objects.filter(
                fk_agricultor=self.usuario_agricultor,
                periodo_inicio=date(2026, 7, 20),
                periodo_fin=date(2026, 7, 26),
            ).count(),
            2,
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
        # Solo cuenta el pedido del 2026-12-28 (100.00), no el del 27 (999.00)
        self.assertEqual(Decimal(data["monto_ventas"]), Decimal("100.00"))
        self.assertEqual(len(data["ventas"]), 1)
        data = resp.json()["data"]
        self.assertEqual(data["periodo_inicio"], "2026-12-28")
        self.assertEqual(data["periodo_fin"], "2027-01-03")
        # Solo cuenta el pedido del 2026-12-28 (100.00)
        self.assertEqual(Decimal(data["monto_ventas"]), Decimal("100.00"))
        self.assertEqual(len(data["ventas"]), 1)


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
            sum(1 for c in codes if c == status.HTTP_409_CONFLICT),
            NUM_THREADS - 1,
            f"Esperaba {NUM_THREADS - 1} conflictos, recibí {results}",
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
