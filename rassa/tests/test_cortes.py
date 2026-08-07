"""Tests para el módulo de Cortes."""

import threading
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from rassa.models import (
    Corte,
    EstadoPedido,
    Log,
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

    def setUp(self):
        # S2: _monto_teorico cachea 60s en LocMemCache (persiste entre tests del
        # mismo proceso); sin limpiarla un test podría leer el valor cacheado de
        # otro test y dar falso-verde o flakiness.
        cache.clear()

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

    def _crear_pago(self, monto, vendedor, fecha=None, tipo=None):
        """Crea un pago directamente en BD, con creado_en controlable."""
        pedido = PedidoCabecera.objects.create(
            fk_cliente=self.usuario_cliente,
            fk_vendedor=vendedor,
            fk_estado=self.estado_entregado,
            subtotal=monto,
            iva=Decimal("0.00"),
            total=monto,
        )
        pago = Pago.objects.create(fk_pedido=pedido, fk_tipo=tipo or self.tipo_efectivo, monto=monto)
        if fecha is not None:
            Pago.objects.filter(pk=pago.pk).update(creado_en=fecha)
        return pago


class CorteCreateTest(CortesTestBase):
    """Tests de creación de cortes."""

    def setUp(self):
        super().setUp()
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

    def test_monto_real_negativo_400(self):
        resp = self.client.post(
            "/api/cortes/",
            {"monto_real": "-10.00", "fecha": str(self.hoy)},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

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
            fecha=timezone.make_aware(timezone.datetime.combine(ayer, timezone.datetime.min.time())),
        )
        resp = self.client.post(
            "/api/cortes/",
            {"monto_real": "100.00", "fecha": str(self.hoy)},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.json()["monto_teorico"], "100.00")

    def test_crear_corte_solo_suma_efectivo(self):
        # S6: el monto teórico del arqueo solo incluye pagos en Efectivo; una
        # transferencia del mismo vendedor el mismo día no debe sumarse.
        self._crear_pago(Decimal("100.00"), self.usuario_vendedor)
        tipo_transferencia = TipoPago.objects.create(id_tipo_pago=2, nombre="Transferencia")
        self._crear_pago(Decimal("50.00"), self.usuario_vendedor, tipo=tipo_transferencia)
        resp = self.client.post(
            "/api/cortes/",
            {"monto_real": "100.00", "fecha": str(self.hoy)},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.json()["monto_teorico"], "100.00")

    def test_crear_corte_incluye_pago_23_59_hora_local(self):
        # Un pago a las 23:59 hora local (settings.TIME_ZONE) pertenece al corte
        # del día local, aunque en UTC ya sea el día siguiente.
        tz = ZoneInfo(getattr(settings, "TIME_ZONE", "UTC"))
        creado_en = timezone.make_aware(datetime.combine(self.hoy, time(23, 59)), tz)
        self._crear_pago(Decimal("88.00"), self.usuario_vendedor, fecha=creado_en)
        resp = self.client.post(
            "/api/cortes/",
            {"monto_real": "88.00", "fecha": str(self.hoy)},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.json()["monto_teorico"], "88.00")

    def test_crear_corte_registra_log_estructurado(self):
        # El audit trail (tabla Log) debe llevar los campos financieros como
        # pares key=value separados, no solo texto interpolado.
        self._crear_pago(Decimal("100.00"), self.usuario_vendedor)
        resp = self.client.post(
            "/api/cortes/",
            {"monto_real": "100.00", "fecha": str(self.hoy)},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        log_entry = Log.objects.filter(descripcion__startswith="corte_creado").latest("creado_en")
        self.assertIn(f"id_corte={resp.json()['id_corte']}", log_entry.descripcion)
        self.assertIn("vendedor_id=", log_entry.descripcion)
        self.assertIn("fecha=", log_entry.descripcion)
        self.assertIn("monto_real=", log_entry.descripcion)
        self.assertIn("monto_teorico=", log_entry.descripcion)
        self.assertIn("diferencia=", log_entry.descripcion)


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
        super().setUp()
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

    def test_vendedor_no_ve_detalle_de_corte_de_otro(self):
        """GET /api/cortes/{id}/ de un corte de otro vendedor devuelve 404."""
        client1 = APIClient()
        client1.force_authenticate(user=self.usuario_vendedor.fk_user)
        resp = client1.post("/api/cortes/", {"monto_real": "100.00", "fecha": str(self.hoy)})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        id_corte = resp.json()["id_corte"]

        client2 = APIClient()
        client2.force_authenticate(user=self.usuario_vendedor2.fk_user)
        detail = client2.get(f"/api/cortes/{id_corte}/")
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)

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
        # R3-002: select_related("fk_vendedor__fk_persona") evita el N+1 de
        # vendedor_nombre. Con el join el listado usa ~2 consultas (count + list);
        # sin él, ~2 más por corte listado. Límite holgado de 4.
        with CaptureQueriesContext(connection) as ctx:
            resp = admin_client.get("/api/cortes/")
        self.assertLessEqual(len(ctx.captured_queries), 4)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["count"], 2)

    def test_corte_incluye_vendedor_nombre(self):
        # S1: el serializer expone el nombre legible del vendedor (nombre +
        # apellido_paterno) en detalle y listado.
        self.client.force_authenticate(user=self.usuario_vendedor.fk_user)
        self._crear_pago(Decimal("100.00"), self.usuario_vendedor)
        resp = self.client.post(
            "/api/cortes/",
            {"monto_real": "100.00", "fecha": str(self.hoy)},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        id_corte = resp.json()["id_corte"]

        detail = self.client.get(f"/api/cortes/{id_corte}/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.json()["vendedor_nombre"], "vendedor Test")

        list_resp = self.client.get("/api/cortes/")
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        results = list_resp.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["vendedor_nombre"], "vendedor Test")


class CorteTeoricoTest(CortesTestBase):
    """Tests del endpoint /api/cortes/teorico/."""

    def setUp(self):
        super().setUp()
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

    def test_teorico_solo_suma_efectivo(self):
        # S6: el teórico solo suma pagos en Efectivo; transferencias/depósitos
        # del mismo vendedor el mismo día quedan fuera del arqueo.
        self._crear_pago(Decimal("100.00"), self.usuario_vendedor)
        tipo_transferencia = TipoPago.objects.create(id_tipo_pago=2, nombre="Transferencia")
        self._crear_pago(Decimal("50.00"), self.usuario_vendedor, tipo=tipo_transferencia)
        resp = self.client.get(f"/api/cortes/teorico/?fecha={self.hoy}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["monto_teorico"], "100.00")

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

    def test_teorico_incluye_pago_23_59_hora_local(self):
        # El pago a las 23:59 hora local cae en el día local; con el filtro
        # __date en UTC (zona de la conexión) quedaría excluido al día siguiente.
        tz = ZoneInfo(getattr(settings, "TIME_ZONE", "UTC"))
        creado_en = timezone.make_aware(datetime.combine(self.hoy, time(23, 59)), tz)
        self._crear_pago(Decimal("77.00"), self.usuario_vendedor, fecha=creado_en)
        resp = self.client.get(f"/api/cortes/teorico/?fecha={self.hoy}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["monto_teorico"], "77.00")


class CorteFKVendedorTest(CortesTestBase):
    """C2: fk_vendedor nullable + UniqueConstraint parcial que excluye NULLs (Opción B)."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(user=self.usuario_vendedor.fk_user)
        self.hoy = timezone.localdate()

    def test_eliminar_vendedor_deja_null_y_conviven_huerfanos_misma_fecha(self):
        # Dos vendedores distintos, misma fecha: ambos cortes conviven.
        Corte.objects.create(
            fk_vendedor=self.usuario_vendedor,
            fecha=self.hoy,
            monto_real=Decimal("10.00"),
            monto_teorico=Decimal("10.00"),
            diferencia=Decimal("0.00"),
        )
        Corte.objects.create(
            fk_vendedor=self.usuario_vendedor2,
            fecha=self.hoy,
            monto_real=Decimal("20.00"),
            monto_teorico=Decimal("20.00"),
            diferencia=Decimal("0.00"),
        )
        # SET_NULL: eliminar el vendedor no borra el corte, deja fk_vendedor NULL.
        self.usuario_vendedor.delete()
        self.usuario_vendedor2.delete()
        self.assertEqual(Corte.objects.filter(fecha=self.hoy, fk_vendedor__isnull=True).count(), 2)
        # El constraint parcial excluye NULLs: un tercer corte huérfano en la
        # misma fecha también se puede crear (PostgreSQL trata NULL != NULL).
        Corte.objects.create(
            fk_vendedor=None,
            fecha=self.hoy,
            monto_real=Decimal("30.00"),
            monto_teorico=Decimal("30.00"),
            diferencia=Decimal("0.00"),
        )
        self.assertEqual(Corte.objects.filter(fecha=self.hoy).count(), 3)

    def test_vendedor_nombre_none_en_corte_huerfano(self):
        # R3-004: un corte huérfano (fk_vendedor NULL tras eliminar al vendedor)
        # expone vendedor_nombre=None en el detalle sin romper el serializer.
        corte = Corte.objects.create(
            fk_vendedor=None,
            fecha=self.hoy,
            monto_real=Decimal("10.00"),
            monto_teorico=Decimal("10.00"),
            diferencia=Decimal("0.00"),
        )
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
        self.client.force_authenticate(user=user_admin)
        resp = self.client.get(f"/api/cortes/{corte.id_corte}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.json()["vendedor_nombre"])

    def test_dos_vendedores_no_null_misma_fecha_sigue_imposible(self):
        resp = self.client.post(
            "/api/cortes/",
            {"monto_real": "10.00", "fecha": str(self.hoy)},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        resp = self.client.post(
            "/api/cortes/",
            {"monto_real": "10.00", "fecha": str(self.hoy)},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Ya existe un corte", resp.json()["message"])
        self.assertEqual(Corte.objects.filter(fk_vendedor=self.usuario_vendedor).count(), 1)


class CorteConcurrenciaTest(TransactionTestCase):
    """B1: 5 hilos POSTean el mismo corte (mismo vendedor+fecha) simultáneamente.

    TransactionTestCase + `@pytest.mark.django_db(transaction=True)` dan semántica
    de BD real: cada hilo usa su propia conexión y commit independiente, por lo que
    la condición de carrera se reproduce de verdad. Esperado: exactamente 1×201,
    4×400 y nunca 500.
    """

    def _crear_vendedor(self):
        rol = Rol.objects.create(nombre_rol="Vendedor", descripcion="Vendedor")
        persona = Persona.objects.create(
            nombre="Concurrente",
            apellido_paterno="Test",
            sexo="M",
            fecha_nacimiento="1990-01-01",
            domicilio="Calle 1",
        )
        user = User.objects.create_user(username="conc@test.com", email="conc@test.com", password="pass123")
        return Usuario.objects.create(
            fk_user=user,
            fk_persona=persona,
            fk_rol=rol,
            correo="conc@test.com",
        )

    @pytest.mark.django_db(transaction=True)
    def test_creacion_concurrente_mismo_corte(self):
        vendedor = self._crear_vendedor()
        hoy = timezone.localdate()
        n_threads = 5
        barrier = threading.Barrier(n_threads)
        resultados = []
        errores = []
        lock = threading.Lock()

        def post_corte():
            client = APIClient()
            client.force_authenticate(user=vendedor.fk_user)
            try:
                barrier.wait(timeout=30)
                resp = client.post("/api/cortes/", {"monto_real": "10.00", "fecha": str(hoy)})
                with lock:
                    resultados.append(resp.status_code)
            except Exception as exc:  # pragma: no cover — fallo de infraestructura
                with lock:
                    errores.append(repr(exc))
            finally:
                # Cerrar la conexión propia del hilo: connections.close_all() solo
                # cierra las del hilo actual y dejaría 5 sesiones abiertas al teardown.
                connection.close()

        threads = [threading.Thread(target=post_corte) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        # Cerrar la conexión del hilo principal por si quedó registrada.
        connections.close_all()

        self.assertEqual(errores, [], f"Excepciones en hilos: {errores}")
        self.assertEqual(len(resultados), n_threads)
        self.assertEqual(resultados.count(status.HTTP_201_CREATED), 1)
        self.assertEqual(resultados.count(status.HTTP_400_BAD_REQUEST), 4)
        self.assertEqual(resultados.count(status.HTTP_500_INTERNAL_SERVER_ERROR), 0)
        self.assertEqual(Corte.objects.count(), 1)
