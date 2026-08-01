"""Tests para el módulo de Cortes."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from rassa.models import (
    Corte,
    EstadoPedido,
    Pago,
    PedidoCabecera,
    Persona,
    Rol,
    TipoPago,
    Usuario,
)


class CortesTestBase(TestCase):
    """Base class with shared setup for corte tests."""

    @classmethod
    def setUpTestData(cls):
        cls.rol_admin = Rol.objects.create(id_rol=1, nombre_rol="Admin", descripcion="Admin")
        cls.rol_vendedor = Rol.objects.create(id_rol=2, nombre_rol="Vendedor", descripcion="Vendedor")
        cls.rol_cliente = Rol.objects.create(id_rol=3, nombre_rol="Cliente", descripcion="Cliente")

        cls.estado_entregado = EstadoPedido.objects.create(
            id_estado=5, tipo_estado="entregado", descripcion="Entregado"
        )
        cls.tipo_efectivo = TipoPago.objects.create(id_tipo_pago=1, nombre="Efectivo")

        cls.usuario_vendedor = cls._crear_usuario("vendedor@test.com", cls.rol_vendedor)
        cls.usuario_vendedor2 = cls._crear_usuario("vendedor2@test.com", cls.rol_vendedor)
        cls.usuario_cliente = cls._crear_usuario("cliente@test.com", cls.rol_cliente)

    @classmethod
    def _crear_usuario(cls, email, rol):
        persona = Persona.objects.create(
            nombre=email.split("@")[0],
            apellido_paterno="Test",
            sexo="M",
            fecha_nacimiento="1990-01-01",
            domicilio="Calle 1",
        )
        user = User.objects.create_user(username=email, email=email, password="pass123")
        return Usuario.objects.create(fk_user=user, fk_persona=persona, fk_rol=rol, correo=email)

    def _crear_pago(self, monto, vendedor, fecha=None):
        """Crea un pago directamente en BD, con creado_en controlable."""
        pedido = PedidoCabecera.objects.create(
            fk_cliente=self.usuario_cliente,
            fk_vendedor=vendedor,
            fk_estado=self.estado_entregado,
            subtotal=monto,
            iva=Decimal("0.00"),
            total=monto,
        )
        pago = Pago.objects.create(fk_pedido=pedido, fk_tipo=self.tipo_efectivo, monto=monto)
        if fecha is not None:
            Pago.objects.filter(pk=pago.pk).update(creado_en=fecha)
        return pago


class CorteCreateTest(CortesTestBase):
    """Tests de creación de cortes."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.usuario_vendedor.fk_user)
        self.hoy = timezone.localdate()

    def test_crear_corte_hoy(self):
        self._crear_pago(Decimal("100.00"), self.usuario_vendedor)
        self._crear_pago(Decimal("16.00"), self.usuario_vendedor)
        self._crear_pago(Decimal("999.00"), self.usuario_vendedor2)

        resp = self.client.post(
            "/api/cortes/",
            {"monto_real": "120.00", "fecha": str(self.hoy)},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()
        self.assertEqual(data["monto_teorico"], "116.00")
        self.assertEqual(data["diferencia"], "4.00")
        self.assertEqual(data["estado"], "cerrado")
        self.assertEqual(data["fecha"], str(self.hoy))

        corte = Corte.objects.get(pk=data["id_corte"])
        self.assertEqual(corte.fk_vendedor, self.usuario_vendedor)
        self.assertEqual(corte.monto_teorico, Decimal("116.00"))
        self.assertEqual(corte.diferencia, Decimal("4.00"))

    def test_crear_corte_sin_pagos(self):
        resp = self.client.post(
            "/api/cortes/",
            {"monto_real": "0.00", "fecha": str(self.hoy)},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()
        self.assertEqual(data["monto_teorico"], "0.00")
        self.assertEqual(data["diferencia"], "0.00")

    def test_crear_corte_fecha_por_defecto_hoy(self):
        self._crear_pago(Decimal("50.00"), self.usuario_vendedor)
        resp = self.client.post("/api/cortes/", {"monto_real": "50.00"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()
        self.assertEqual(data["fecha"], str(self.hoy))
        self.assertEqual(data["monto_teorico"], "50.00")

    def test_crear_corte_duplicado_400(self):
        self.client.post(
            "/api/cortes/",
            {"monto_real": "10.00", "fecha": str(self.hoy)},
        )
        resp = self.client.post(
            "/api/cortes/",
            {"monto_real": "10.00", "fecha": str(self.hoy)},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Ya existe un corte", resp.json()["message"])
        self.assertEqual(Corte.objects.filter(fk_vendedor=self.usuario_vendedor).count(), 1)

    def test_mismo_vendedor_puede_crear_corte_otro_dia(self):
        self.client.post(
            "/api/cortes/",
            {"monto_real": "10.00", "fecha": str(self.hoy)},
        )
        ayer = self.hoy - timedelta(days=1)
        resp = self.client.post(
            "/api/cortes/",
            {"monto_real": "10.00", "fecha": str(ayer)},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_monto_teorico_solo_suma_pagos_de_ese_dia(self):
        self._crear_pago(Decimal("100.00"), self.usuario_vendedor)
        ayer = self.hoy - timedelta(days=1)
        self._crear_pago(
            Decimal("50.00"),
            self.usuario_vendedor,
            fecha=timezone.make_aware(
                timezone.datetime.combine(ayer, timezone.datetime.min.time())
            ),
        )
        resp = self.client.post(
            "/api/cortes/",
            {"monto_real": "100.00", "fecha": str(self.hoy)},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.json()["monto_teorico"], "100.00")


class CortePermisosTest(CortesTestBase):
    """Tests de permisos del endpoint de cortes."""

    def setUp(self):
        self.client = APIClient()
        self.hoy = timezone.localdate()

    def test_no_autenticado_401(self):
        resp = self.client.get("/api/cortes/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_no_autenticado_no_puede_crear(self):
        resp = self.client.post("/api/cortes/", {"monto_real": "10.00"})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_no_autenticado_teorico_401(self):
        resp = self.client.get("/api/cortes/teorico/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cliente_no_puede_ver_cortes(self):
        self.client.force_authenticate(user=self.usuario_cliente.fk_user)
        resp = self.client.get("/api/cortes/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class CorteListTest(CortesTestBase):
    """Tests de listado de cortes."""

    def setUp(self):
        self.client = APIClient()
        self.hoy = timezone.localdate()

    def test_vendedor_solo_ve_sus_cortes(self):
        self._crear_pago(Decimal("100.00"), self.usuario_vendedor)
        self._crear_pago(Decimal("200.00"), self.usuario_vendedor2)

        client1 = APIClient()
        client1.force_authenticate(user=self.usuario_vendedor.fk_user)
        client1.post("/api/cortes/", {"monto_real": "100.00", "fecha": str(self.hoy)})

        client2 = APIClient()
        client2.force_authenticate(user=self.usuario_vendedor2.fk_user)
        client2.post("/api/cortes/", {"monto_real": "200.00", "fecha": str(self.hoy)})

        resp = client1.get("/api/cortes/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["monto_teorico"], "100.00")

    def test_admin_ve_todos_los_cortes(self):
        persona = Persona.objects.create(
            nombre="Admin",
            apellido_paterno="Test",
            sexo="M",
            fecha_nacimiento="1990-01-01",
            domicilio="Calle 2",
        )
        user_admin = User.objects.create_user(username="admin@test.com", email="admin@test.com", password="pass123")
        Usuario.objects.create(
            fk_user=user_admin,
            fk_persona=persona,
            fk_rol=self.rol_admin,
            correo="admin@test.com",
        )

        client1 = APIClient()
        client1.force_authenticate(user=self.usuario_vendedor.fk_user)
        client1.post("/api/cortes/", {"monto_real": "10.00", "fecha": str(self.hoy)})
        client2 = APIClient()
        client2.force_authenticate(user=self.usuario_vendedor2.fk_user)
        client2.post("/api/cortes/", {"monto_real": "20.00", "fecha": str(self.hoy)})

        admin_client = APIClient()
        admin_client.force_authenticate(user=user_admin)
        resp = admin_client.get("/api/cortes/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["count"], 2)


class CorteTeoricoTest(CortesTestBase):
    """Tests del endpoint /api/cortes/teorico/."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.usuario_vendedor.fk_user)
        self.hoy = timezone.localdate()

    def test_teorico_suma_pagos_del_vendedor(self):
        self._crear_pago(Decimal("100.00"), self.usuario_vendedor)
        self._crear_pago(Decimal("16.00"), self.usuario_vendedor)
        self._crear_pago(Decimal("999.00"), self.usuario_vendedor2)

        resp = self.client.get(f"/api/cortes/teorico/?fecha={self.hoy}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["fecha"], str(self.hoy))
        self.assertEqual(data["monto_teorico"], "116.00")

    def test_teorico_sin_fecha_usa_hoy(self):
        self._crear_pago(Decimal("40.00"), self.usuario_vendedor)
        resp = self.client.get("/api/cortes/teorico/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["fecha"], str(self.hoy))
        self.assertEqual(data["monto_teorico"], "40.00")

    def test_teorico_fecha_invalida_400(self):
        resp = self.client.get("/api/cortes/teorico/?fecha=31/12/2026")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_teorico_sin_pagos_es_cero(self):
        resp = self.client.get(f"/api/cortes/teorico/?fecha={self.hoy}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["monto_teorico"], "0.00")
