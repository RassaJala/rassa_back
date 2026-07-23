"""Pruebas unitarias para el módulo de Pedidos."""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import DatabaseError
from rest_framework import status
from rest_framework.test import APITestCase

from rassa.models import EstadoPedido, HistorialEstadoPedido, PedidoCabecera, Persona, Rol, Usuario


class PedidosTestCase(APITestCase):
    """Caso de prueba para la gestión de Pedidos."""

    def setUp(self):
        # Roles
        self.rol_admin = Rol.objects.create(nombre_rol="Admin", descripcion="Administrador")
        self.rol_vendedor = Rol.objects.create(nombre_rol="Vendedor", descripcion="Vendedor")
        self.rol_cliente = Rol.objects.create(nombre_rol="Cliente", descripcion="Cliente")

        # Estados de pedido
        self.estado_pendiente = EstadoPedido.objects.create(tipo_estado="pendiente", descripcion="Pendiente")
        self.estado_confirmado = EstadoPedido.objects.create(tipo_estado="confirmado", descripcion="Confirmado")
        self.estado_en_preparacion = EstadoPedido.objects.create(
            tipo_estado="en_preparacion", descripcion="En preparación"
        )
        self.estado_listo = EstadoPedido.objects.create(
            tipo_estado="listo_para_retirar", descripcion="Listo para retirar"
        )
        self.estado_entregado = EstadoPedido.objects.create(tipo_estado="entregado", descripcion="Entregado")
        self.estado_cancelado = EstadoPedido.objects.create(tipo_estado="cancelado", descripcion="Cancelado")

        # Usuarios
        self.user_admin = User.objects.create_superuser(
            username="admin", email="admin@rassa.com", password="password123"
        )
        self.persona_admin = Persona.objects.create(
            nombre="Admin", apellido_paterno="Rassa", fecha_nacimiento="1990-01-01", sexo="M", domicilio="Calle 1"
        )
        self.usuario_admin = Usuario.objects.create(
            fk_user=self.user_admin,
            fk_persona=self.persona_admin,
            telefono="1234567890",
            correo="admin@rassa.com",
            fk_rol=self.rol_admin,
        )

        self.user_vendedor = User.objects.create_user(
            username="vendedor1", email="vendedor1@rassa.com", password="password123"
        )
        self.persona_vendedor = Persona.objects.create(
            nombre="Juan", apellido_paterno="Perez", fecha_nacimiento="1985-03-10", sexo="M", domicilio="Calle 2"
        )
        self.usuario_vendedor = Usuario.objects.create(
            fk_user=self.user_vendedor,
            fk_persona=self.persona_vendedor,
            telefono="0987654321",
            correo="vendedor1@rassa.com",
            fk_rol=self.rol_vendedor,
        )

        self.user_cliente = User.objects.create_user(
            username="cliente1", email="cliente1@rassa.com", password="password123"
        )
        self.persona_cliente = Persona.objects.create(
            nombre="Maria", apellido_paterno="Garcia", fecha_nacimiento="1995-05-05", sexo="F", domicilio="Calle 3"
        )
        self.usuario_cliente = Usuario.objects.create(
            fk_user=self.user_cliente,
            fk_persona=self.persona_cliente,
            telefono="1122334455",
            correo="cliente1@rassa.com",
            fk_rol=self.rol_cliente,
        )

        # Pedido de prueba (pertenece a vendedor1)
        self.pedido = PedidoCabecera.objects.create(
            fk_cliente=self.usuario_cliente,
            fk_estado=self.estado_pendiente,
            fk_vendedor=self.usuario_vendedor,
            subtotal=Decimal("100.00"),
            iva=Decimal("21.00"),
            total=Decimal("121.00"),
        )

    def _crear_usuario_vendedor(self, username):
        user = User.objects.create_user(username=username, email=f"{username}@rassa.com", password="password123")
        persona = Persona.objects.create(
            nombre="Otro", apellido_paterno="Vendedor", fecha_nacimiento="1980-01-01", sexo="M", domicilio="Calle 4"
        )
        usuario = Usuario.objects.create(
            fk_user=user,
            fk_persona=persona,
            telefono="5555555555",
            correo=f"{username}@rassa.com",
            fk_rol=self.rol_vendedor,
        )
        return user, usuario

    # ── Listar pedidos ──────────────────────────────────────

    def test_listar_pedidos_como_vendedor(self):
        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.get("/api/pedidos/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id_pedido"], self.pedido.id_pedido)

    def test_listar_pedidos_como_admin(self):
        self.client.force_authenticate(user=self.user_admin)
        response = self.client.get("/api/pedidos/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_listar_pedidos_filtrado_por_estado(self):
        self.client.force_authenticate(user=self.user_admin)
        response = self.client.get("/api/pedidos/", {"estado": "pendiente"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

        response_vacio = self.client.get("/api/pedidos/", {"estado": "entregado"}, format="json")
        self.assertEqual(response_vacio.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_vacio.data["results"]), 0)

    def test_listar_pedidos_vendedor_no_ve_otros(self):
        _, usuario_vendedor2 = self._crear_usuario_vendedor("vendedor2")
        PedidoCabecera.objects.create(
            fk_cliente=self.usuario_cliente,
            fk_estado=self.estado_pendiente,
            fk_vendedor=usuario_vendedor2,
            subtotal=Decimal("50.00"),
            iva=Decimal("10.50"),
            total=Decimal("60.50"),
        )

        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.get("/api/pedidos/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    # ── Detalle pedido ──────────────────────────────────────

    def test_detalle_pedido(self):
        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.get(f"/api/pedidos/{self.pedido.id_pedido}/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id_pedido"], self.pedido.id_pedido)
        self.assertEqual(response.data["estado_actual"], "pendiente")
        self.assertIn("detalles", response.data)
        self.assertIn("historial", response.data)

    def test_detalle_pedido_no_existente(self):
        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.get("/api/pedidos/99999/", format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ── Cambiar estado — transiciones válidas ────────────────

    def test_cambiar_estado_pendiente_a_confirmado(self):
        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "confirmado"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.fk_estado.tipo_estado, "confirmado")

    def test_cambiar_estado_confirmado_a_en_preparacion(self):
        self.pedido.fk_estado = self.estado_confirmado
        self.pedido.save(update_fields=["fk_estado"])

        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "en_preparacion"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.fk_estado.tipo_estado, "en_preparacion")

    def test_cambiar_estado_en_preparacion_a_listo(self):
        self.pedido.fk_estado = self.estado_en_preparacion
        self.pedido.save(update_fields=["fk_estado"])

        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "listo_para_retirar"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.fk_estado.tipo_estado, "listo_para_retirar")

    def test_cambiar_estado_listo_a_entregado(self):
        self.pedido.fk_estado = self.estado_listo
        self.pedido.save(update_fields=["fk_estado"])

        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "entregado"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.fk_estado.tipo_estado, "entregado")

    # ── Admin cambiar estado ─────────────────────────────────

    def test_admin_cambiar_estado(self):
        self.client.force_authenticate(user=self.user_admin)
        response = self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "confirmado"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.fk_estado.tipo_estado, "confirmado")

    # ── Cancelación ─────────────────────────────────────────

    def test_cancelar_pedido_pendiente(self):
        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "cancelado"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.fk_estado.tipo_estado, "cancelado")

    def test_cancelar_pedido_confirmado(self):
        self.pedido.fk_estado = self.estado_confirmado
        self.pedido.save(update_fields=["fk_estado"])

        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "cancelado"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_cancelar_pedido_en_preparacion(self):
        self.pedido.fk_estado = self.estado_en_preparacion
        self.pedido.save(update_fields=["fk_estado"])

        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "cancelado"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_cancelar_pedido_listo(self):
        self.pedido.fk_estado = self.estado_listo
        self.pedido.save(update_fields=["fk_estado"])

        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "cancelado"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ── DatabaseError ────────────────────────────────────────

    def test_database_error_retorna_409(self):
        self.client.force_authenticate(user=self.user_vendedor)
        with patch.object(PedidoCabecera.objects, "select_for_update", side_effect=DatabaseError) as mock_lock:
            response = self.client.patch(
                f"/api/pedidos/{self.pedido.id_pedido}/status/",
                {"nuevo_estado": "confirmado"},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
            mock_lock.assert_called()

    # ── Cross-seller ─────────────────────────────────────────

    def test_vendedor_no_ve_detalle_de_otro_vendedor(self):
        _, usuario_vendedor2 = self._crear_usuario_vendedor("vendedor2")
        pedido_otro = PedidoCabecera.objects.create(
            fk_cliente=self.usuario_cliente,
            fk_estado=self.estado_pendiente,
            fk_vendedor=usuario_vendedor2,
            subtotal=Decimal("50.00"),
            iva=Decimal("10.50"),
            total=Decimal("60.50"),
        )

        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.get(f"/api/pedidos/{pedido_otro.id_pedido}/", format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_vendedor_no_cambia_estado_de_otro_vendedor(self):
        _, usuario_vendedor2 = self._crear_usuario_vendedor("vendedor2")
        pedido_otro = PedidoCabecera.objects.create(
            fk_cliente=self.usuario_cliente,
            fk_estado=self.estado_pendiente,
            fk_vendedor=usuario_vendedor2,
            subtotal=Decimal("50.00"),
            iva=Decimal("10.50"),
            total=Decimal("60.50"),
        )

        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.patch(
            f"/api/pedidos/{pedido_otro.id_pedido}/status/",
            {"nuevo_estado": "confirmado"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ── Pedido inexistente ───────────────────────────────────

    def test_cambiar_estado_pedido_inexistente(self):
        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.patch(
            "/api/pedidos/99999/status/",
            {"nuevo_estado": "confirmado"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ── Transiciones inválidas ──────────────────────────────

    def test_transicion_invalida_salto(self):
        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "en_preparacion"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_transicion_invalida_reversa(self):
        self.pedido.fk_estado = self.estado_confirmado
        self.pedido.save(update_fields=["fk_estado"])

        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "pendiente"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_transicion_estado_terminal(self):
        self.pedido.fk_estado = self.estado_entregado
        self.pedido.save(update_fields=["fk_estado"])

        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "pendiente"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancelar_pedido_ya_cancelado(self):
        self.pedido.fk_estado = self.estado_cancelado
        self.pedido.save(update_fields=["fk_estado"])

        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "cancelado"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_estado_invalido(self):
        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "estado_fantasma"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Historial ───────────────────────────────────────────

    def test_historial_se_crea_al_cambiar_estado(self):
        self.client.force_authenticate(user=self.user_vendedor)
        self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "confirmado"},
            format="json",
        )
        historial = HistorialEstadoPedido.objects.filter(fk_pedido=self.pedido)
        self.assertEqual(historial.count(), 1)
        h = historial.first()
        self.assertEqual(h.fk_estado_anterior.tipo_estado, "pendiente")
        self.assertEqual(h.fk_estado_nuevo.tipo_estado, "confirmado")
        self.assertEqual(h.fk_cambiado_por, self.usuario_vendedor)

    def test_historial_en_respuesta_api(self):
        self.client.force_authenticate(user=self.user_vendedor)
        self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "confirmado"},
            format="json",
        )
        response = self.client.get(f"/api/pedidos/{self.pedido.id_pedido}/", format="json")
        self.assertIn("historial", response.data)
        self.assertEqual(len(response.data["historial"]), 1)
        entrada = response.data["historial"][0]
        self.assertEqual(entrada["estado_anterior"], "pendiente")
        self.assertEqual(entrada["estado_nuevo"], "confirmado")
        self.assertEqual(entrada["cambiado_por_nombre"], "Juan Perez")

    # ── Permisos ────────────────────────────────────────────

    def test_cliente_no_puede_acceder(self):
        self.client.force_authenticate(user=self.user_cliente)
        response = self.client.get("/api/pedidos/", format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_usuario_no_autenticado(self):
        response = self.client.get("/api/pedidos/", format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ── Serializer ──────────────────────────────────────────

    def test_list_serializer_campos(self):
        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.get("/api/pedidos/", format="json")
        item = response.data["results"][0]
        self.assertIn("id_pedido", item)
        self.assertIn("cliente_nombre", item)
        self.assertIn("vendedor_nombre", item)
        self.assertIn("total", item)
        self.assertIn("estado_actual", item)
        self.assertIn("creado_en", item)

    def test_list_serializer_nombres(self):
        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.get("/api/pedidos/", format="json")
        item = response.data["results"][0]
        self.assertEqual(item["cliente_nombre"], "Maria Garcia")
        self.assertEqual(item["vendedor_nombre"], "Juan Perez")
