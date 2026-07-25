"""Pruebas unitarias para el módulo de Pedidos."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import DatabaseError
from rest_framework import status
from rest_framework.test import APITestCase

from rassa.models import (
    CategoriaProducto,
    DetallePedido,
    EstadoPedido,
    HistorialEstadoPedido,
    LimiteCliente,
    PedidoCabecera,
    Persona,
    Producto,
    ProductoSemanal,
    PublicacionSemanal,
    Rol,
    Unidad,
    Usuario,
)


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

    def test_cliente_lista_sus_pedidos(self):
        self.client.force_authenticate(user=self.user_cliente)
        response = self.client.get("/api/pedidos/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id_pedido"], self.pedido.id_pedido)
        self.assertIn("productos", response.data["results"][0])

    def test_cliente_solo_ve_sus_pedidos(self):
        otro_cliente_user = User.objects.create_user(
            username="cliente2", email="cliente2@rassa.com", password="password123"
        )
        otro_persona = Persona.objects.create(
            nombre="Pedro", apellido_paterno="Lopez", fecha_nacimiento="1992-02-02", sexo="M", domicilio="Calle 5"
        )
        otro_cliente = Usuario.objects.create(
            fk_user=otro_cliente_user,
            fk_persona=otro_persona,
            telefono="6677889900",
            correo="cliente2@rassa.com",
            fk_rol=self.rol_cliente,
        )
        PedidoCabecera.objects.create(
            fk_cliente=otro_cliente,
            fk_estado=self.estado_pendiente,
            fk_vendedor=self.usuario_vendedor,
            subtotal=Decimal("50.00"),
            iva=Decimal("10.50"),
            total=Decimal("60.50"),
        )

        self.client.force_authenticate(user=self.user_cliente)
        response = self.client.get("/api/pedidos/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_cliente_ve_detalle_de_su_pedido(self):
        self.client.force_authenticate(user=self.user_cliente)
        response = self.client.get(f"/api/pedidos/{self.pedido.id_pedido}/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id_pedido"], self.pedido.id_pedido)
        self.assertIn("detalles", response.data)
        self.assertIn("historial", response.data)

    def test_cliente_no_ve_detalle_de_otro_cliente(self):
        otro_cliente_user = User.objects.create_user(
            username="cliente3", email="cliente3@rassa.com", password="password123"
        )
        otro_persona = Persona.objects.create(
            nombre="Ana", apellido_paterno="Martinez", fecha_nacimiento="1993-03-03", sexo="F", domicilio="Calle 6"
        )
        otro_cliente = Usuario.objects.create(
            fk_user=otro_cliente_user,
            fk_persona=otro_persona,
            telefono="9988776655",
            correo="cliente3@rassa.com",
            fk_rol=self.rol_cliente,
        )
        pedido_otro = PedidoCabecera.objects.create(
            fk_cliente=otro_cliente,
            fk_estado=self.estado_pendiente,
            fk_vendedor=self.usuario_vendedor,
            subtotal=Decimal("50.00"),
            iva=Decimal("10.50"),
            total=Decimal("60.50"),
        )

        self.client.force_authenticate(user=self.user_cliente)
        response = self.client.get(f"/api/pedidos/{pedido_otro.id_pedido}/", format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cliente_no_puede_cambiar_estado(self):
        self.client.force_authenticate(user=self.user_cliente)
        response = self.client.patch(
            f"/api/pedidos/{self.pedido.id_pedido}/status/",
            {"nuevo_estado": "confirmado"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.fk_estado.tipo_estado, "pendiente")

    def test_cliente_lista_vacia(self):
        user_vacio = User.objects.create_user(username="cliente_vacio", email="vacio@rassa.com", password="password123")
        persona_vacia = Persona.objects.create(
            nombre="Sin", apellido_paterno="Pedidos", fecha_nacimiento="1990-01-01", sexo="M", domicilio="Calle 0"
        )
        Usuario.objects.create(
            fk_user=user_vacio,
            fk_persona=persona_vacia,
            telefono="0000000000",
            correo="vacio@rassa.com",
            fk_rol=self.rol_cliente,
        )
        self.client.force_authenticate(user=user_vacio)
        response = self.client.get("/api/pedidos/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)

    def test_cliente_productos_truncados(self):
        from datetime import date

        from rassa.models import CategoriaProducto, Producto, ProductoSemanal, PublicacionSemanal, Unidad

        categoria = CategoriaProducto.objects.create(nombre="Test")
        producto = Producto.objects.create(nombre_producto="Test", fk_categoria=categoria, es_perecedero=False)
        unidad = Unidad.objects.create(nombre="Pieza", abreviatura="pz", tipo="Unidad")
        publicacion = PublicacionSemanal.objects.create(fecha_publicacion=date(2026, 1, 1), semana=1)
        prod_semanal = ProductoSemanal.objects.create(
            fk_publicacion=publicacion,
            fk_producto=producto,
            fk_unidad=unidad,
            stock=10,
            precio=Decimal("10.00"),
        )

        pedido_con_muchos = PedidoCabecera.objects.create(
            fk_cliente=self.usuario_cliente,
            fk_estado=self.estado_pendiente,
            fk_vendedor=self.usuario_vendedor,
            subtotal=Decimal("200.00"),
            iva=Decimal("42.00"),
            total=Decimal("242.00"),
        )
        for i in range(4):
            DetallePedido.objects.create(
                fk_pedido=pedido_con_muchos,
                fk_producto_semanal=prod_semanal,
                nombre_producto=f"Producto {i + 1}",
                precio_unitario=Decimal("50.00"),
                cantidad=1,
                importe=Decimal("50.00"),
            )

        self.client.force_authenticate(user=self.user_cliente)
        response = self.client.get("/api/pedidos/", format="json")
        results = [r for r in response.data["results"] if r["id_pedido"] == pedido_con_muchos.id_pedido]
        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(len(item["productos"]), 3)
        self.assertEqual(item["productos"], ["Producto 1", "Producto 2", "Producto 3"])
        self.assertTrue(item["has_more_productos"])

    def test_cliente_productos_vacios(self):
        pedido_sin_detalles = PedidoCabecera.objects.create(
            fk_cliente=self.usuario_cliente,
            fk_estado=self.estado_pendiente,
            fk_vendedor=self.usuario_vendedor,
            subtotal=Decimal("0.00"),
            iva=Decimal("0.00"),
            total=Decimal("0.00"),
        )

        self.client.force_authenticate(user=self.user_cliente)
        response = self.client.get("/api/pedidos/", format="json")
        results = [r for r in response.data["results"] if r["id_pedido"] == pedido_sin_detalles.id_pedido]
        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item["productos"], [])
        self.assertFalse(item["has_more_productos"])

    def test_cliente_pedido_inexistente(self):
        self.client.force_authenticate(user=self.user_cliente)
        response = self.client.get("/api/pedidos/99999/", format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

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
        self.assertIn("productos", item)
        self.assertIn("has_more_productos", item)
        self.assertIn("total", item)
        self.assertIn("estado_actual", item)
        self.assertIn("creado_en", item)

    def test_list_serializer_nombres(self):
        self.client.force_authenticate(user=self.user_vendedor)
        response = self.client.get("/api/pedidos/", format="json")
        item = response.data["results"][0]
        self.assertEqual(item["cliente_nombre"], "Maria Garcia")
        self.assertEqual(item["vendedor_nombre"], "Juan Perez")


class PedidoCreateTestCase(APITestCase):
    """Tests para POST /api/pedidos/ — creación de pedidos."""

    def setUp(self):
        # Roles
        self.rol_admin = Rol.objects.create(nombre_rol="Admin", descripcion="Administrador")
        self.rol_vendedor = Rol.objects.create(nombre_rol="Vendedor", descripcion="Vendedor")
        self.rol_cliente = Rol.objects.create(nombre_rol="Cliente", descripcion="Cliente")

        # Estado de pedido — pk=1 porque el view hardcodea ESTADO_PENDIENTE_ID = 1
        self.estado_pendiente, _ = EstadoPedido.objects.get_or_create(
            pk=1, defaults={"tipo_estado": "pendiente", "descripcion": "Pendiente"}
        )

        # Categoría y unidad
        self.categoria = CategoriaProducto.objects.create(nombre="Frutas")
        self.unidad = Unidad.objects.create(nombre="Kilogramo", abreviatura="kg", tipo="Peso")

        # Producto del catálogo
        self.producto = Producto.objects.create(
            nombre_producto="Manzana",
            fk_categoria=self.categoria,
            es_perecedero=True,
            precio=Decimal("10.00"),
            stock=100,
        )

        # Publicación semanal (publicada)
        self.publicacion = PublicacionSemanal.objects.create(
            fecha_publicacion=date(2026, 7, 26),
            semana=30,
            estado="publicado",
        )

        # Producto semanal activo con stock
        self.producto_semanal = ProductoSemanal.objects.create(
            fk_publicacion=self.publicacion,
            fk_producto=self.producto,
            fk_unidad=self.unidad,
            stock=50,
            precio=Decimal("20.00"),
            estado="activo",
        )

        # Segundo producto semanal
        self.producto2 = Producto.objects.create(
            nombre_producto="Pera",
            fk_categoria=self.categoria,
            es_perecedero=True,
            precio=Decimal("8.00"),
            stock=100,
        )
        self.producto_semanal2 = ProductoSemanal.objects.create(
            fk_publicacion=self.publicacion,
            fk_producto=self.producto2,
            fk_unidad=self.unidad,
            stock=30,
            precio=Decimal("15.00"),
            estado="activo",
        )

        # Cliente con límite de crédito
        self.user_cliente = User.objects.create_user(
            username="cliente_create", email="cliente_create@rassa.com", password="password123"
        )
        self.persona_cliente = Persona.objects.create(
            nombre="Laura", apellido_paterno="Create", fecha_nacimiento="1995-05-05", sexo="F", domicilio="Calle Test"
        )
        self.usuario_cliente = Usuario.objects.create(
            fk_user=self.user_cliente,
            fk_persona=self.persona_cliente,
            telefono="1111111111",
            correo="cliente_create@rassa.com",
            fk_rol=self.rol_cliente,
        )
        self.limite = LimiteCliente.objects.create(fk_usuario=self.usuario_cliente, monto=Decimal("1000.00"))

        # Vendedor (para referencia)
        self.user_vendedor = User.objects.create_user(
            username="vendedor_create", email="vendedor_create@rassa.com", password="password123"
        )
        self.persona_vendedor = Persona.objects.create(
            nombre="Carlos",
            apellido_paterno="Vende",
            fecha_nacimiento="1985-03-10",
            sexo="M",
            domicilio="Calle Vendedor",
        )
        self.usuario_vendedor = Usuario.objects.create(
            fk_user=self.user_vendedor,
            fk_persona=self.persona_vendedor,
            telefono="2222222222",
            correo="vendedor_create@rassa.com",
            fk_rol=self.rol_vendedor,
        )

        # Admin
        self.user_admin = User.objects.create_superuser(
            username="admin_create", email="admin_create@rassa.com", password="password123"
        )
        self.persona_admin = Persona.objects.create(
            nombre="Admin", apellido_paterno="Create", fecha_nacimiento="1990-01-01", sexo="M", domicilio="Calle Admin"
        )
        self.usuario_admin = Usuario.objects.create(
            fk_user=self.user_admin,
            fk_persona=self.persona_admin,
            telefono="3333333333",
            correo="admin_create@rassa.com",
            fk_rol=self.rol_admin,
        )

    def _crear_payload(self, items):
        return {"items": items}

    # ── Happy path ────────────────────────────────────────────

    def test_crear_pedido_exitoso(self):
        self.client.force_authenticate(user=self.user_cliente)
        payload = self._crear_payload(
            [
                {"id_producto_semanal": self.producto_semanal.id_producto_semanal, "cantidad": 2},
            ]
        )
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("data", response.data)
        data = response.data["data"]
        self.assertEqual(data["cliente_nombre"], "Laura Create")
        self.assertEqual(data["estado"], "pendiente")
        self.assertEqual(Decimal(str(data["subtotal"])), Decimal("40.00"))
        self.assertEqual(Decimal(str(data["iva"])), Decimal("8.40"))  # 21% de 40
        self.assertEqual(Decimal(str(data["total"])), Decimal("48.40"))
        self.assertIn("detalles", data)
        self.assertEqual(len(data["detalles"]), 1)

    def test_crear_pedido_multiples_items(self):
        self.client.force_authenticate(user=self.user_cliente)
        payload = self._crear_payload(
            [
                {"id_producto_semanal": self.producto_semanal.id_producto_semanal, "cantidad": 2},
                {"id_producto_semanal": self.producto_semanal2.id_producto_semanal, "cantidad": 3},
            ]
        )
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data["data"]
        self.assertEqual(len(data["detalles"]), 2)
        # subtotal = 2*20 + 3*15 = 85
        self.assertEqual(Decimal(str(data["subtotal"])), Decimal("85.00"))
        # iva = 85 * 0.21 = 17.85
        self.assertEqual(Decimal(str(data["iva"])), Decimal("17.85"))
        # total = 85 + 17.85 = 102.85
        self.assertEqual(Decimal(str(data["total"])), Decimal("102.85"))

    def test_crear_pedido_descuenta_stock(self):
        self.client.force_authenticate(user=self.user_cliente)
        payload = self._crear_payload(
            [
                {"id_producto_semanal": self.producto_semanal.id_producto_semanal, "cantidad": 5},
            ]
        )
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.producto_semanal.refresh_from_db()
        self.assertEqual(self.producto_semanal.stock, 45)  # 50 - 5

    def test_crear_pedido_crea_historial(self):
        self.client.force_authenticate(user=self.user_cliente)
        payload = self._crear_payload(
            [
                {"id_producto_semanal": self.producto_semanal.id_producto_semanal, "cantidad": 1},
            ]
        )
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        pedido_id = response.data["data"]["id_pedido"]
        historial = HistorialEstadoPedido.objects.filter(fk_pedido_id=pedido_id)
        self.assertEqual(historial.count(), 1)
        h = historial.first()
        self.assertIsNone(h.fk_estado_anterior)
        self.assertEqual(h.fk_estado_nuevo.tipo_estado, "pendiente")

    # ── Validaciones ──────────────────────────────────────────

    def test_crear_pedido_sin_auth(self):
        payload = self._crear_payload(
            [
                {"id_producto_semanal": self.producto_semanal.id_producto_semanal, "cantidad": 1},
            ]
        )
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_crear_pedido_como_vendedor(self):
        self.client.force_authenticate(user=self.user_vendedor)
        payload = self._crear_payload(
            [
                {"id_producto_semanal": self.producto_semanal.id_producto_semanal, "cantidad": 1},
            ]
        )
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_crear_pedido_como_admin(self):
        self.client.force_authenticate(user=self.user_admin)
        payload = self._crear_payload(
            [
                {"id_producto_semanal": self.producto_semanal.id_producto_semanal, "cantidad": 1},
            ]
        )
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_stock_insuficiente(self):
        self.client.force_authenticate(user=self.user_cliente)
        payload = self._crear_payload(
            [
                {"id_producto_semanal": self.producto_semanal.id_producto_semanal, "cantidad": 999},
            ]
        )
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_producto_inexistente(self):
        self.client.force_authenticate(user=self.user_cliente)
        payload = self._crear_payload(
            [
                {"id_producto_semanal": 99999, "cantidad": 1},
            ]
        )
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_producto_inactivo(self):
        self.producto_semanal.estado = "inactivo"
        self.producto_semanal.save(update_fields=["estado"])
        self.client.force_authenticate(user=self.user_cliente)
        payload = self._crear_payload(
            [
                {"id_producto_semanal": self.producto_semanal.id_producto_semanal, "cantidad": 1},
            ]
        )
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_publicacion_no_disponible(self):
        self.publicacion.estado = "borrador"
        self.publicacion.save(update_fields=["estado"])
        self.client.force_authenticate(user=self.user_cliente)
        payload = self._crear_payload(
            [
                {"id_producto_semanal": self.producto_semanal.id_producto_semanal, "cantidad": 1},
            ]
        )
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_items_vacios(self):
        self.client.force_authenticate(user=self.user_cliente)
        payload = self._crear_payload([])
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Límite de crédito ─────────────────────────────────────

    def test_credito_excede_limite(self):
        self.client.force_authenticate(user=self.user_cliente)
        # producto vale 20 c/u, 60 unidades = 1200 de subtotal + IVA
        payload = self._crear_payload(
            [
                {"id_producto_semanal": self.producto_semanal.id_producto_semanal, "cantidad": 60},
            ]
        )
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # DRF ValidationError devuelve el mensaje como string o lista
        self.assertIn("límite de crédito", str(response.data).lower())

    def test_credito_en_limite(self):
        # límite = 1000, con 47 unidades de 20 = 940 + 21% IVA = 1137.40 → excede
        # Con 41 unidades de 20 = 820 + 21% IVA = 992.20 → dentro del límite
        self.client.force_authenticate(user=self.user_cliente)
        payload = self._crear_payload(
            [
                {"id_producto_semanal": self.producto_semanal.id_producto_semanal, "cantidad": 41},
            ]
        )
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_sin_limite_asignado(self):
        """Usuario sin LimiteCliente asociado puede crear pedidos."""
        user_sin_limite = User.objects.create_user(
            username="sin_limite", email="sin_limite@rassa.com", password="password123"
        )
        persona = Persona.objects.create(
            nombre="Sin", apellido_paterno="Limite", fecha_nacimiento="1990-01-01", sexo="M", domicilio="Calle Sin"
        )
        Usuario.objects.create(
            fk_user=user_sin_limite,
            fk_persona=persona,
            telefono="4444444444",
            correo="sin_limite@rassa.com",
            fk_rol=self.rol_cliente,
        )
        self.client.force_authenticate(user=user_sin_limite)
        payload = self._crear_payload(
            [
                {"id_producto_semanal": self.producto_semanal.id_producto_semanal, "cantidad": 1},
            ]
        )
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_credito_excede_con_pedidos_pendientes(self):
        """Cliente con pedido pendiente previo que sumado excede el límite."""
        self.client.force_authenticate(user=self.user_cliente)
        # Crear un pedido previo de $500
        PedidoCabecera.objects.create(
            fk_cliente=self.usuario_cliente,
            fk_estado=self.estado_pendiente,
            subtotal=Decimal("413.22"),
            iva=Decimal("86.78"),
            total=Decimal("500.00"),
        )
        # Ahora intentar otro pedido de $600 → suma 1100 > 1000
        # 30 unidades de 20 = 600 + IVA 126 = 726 pero el límite es 1000 y ya gastó 500
        payload = self._crear_payload(
            [
                {"id_producto_semanal": self.producto_semanal.id_producto_semanal, "cantidad": 30},
            ]
        )
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("límite de crédito", str(response.data).lower())

    # ── Campos de salida del serializer ───────────────────────

    def test_output_serializer_usa_nombres_no_ids(self):
        self.client.force_authenticate(user=self.user_cliente)
        payload = self._crear_payload(
            [
                {"id_producto_semanal": self.producto_semanal.id_producto_semanal, "cantidad": 1},
            ]
        )
        response = self.client.post("/api/pedidos/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data["data"]
        self.assertIn("cliente_nombre", data)
        self.assertIn("estado", data)
        self.assertNotIn("fk_cliente", data)
        self.assertNotIn("fk_estado", data)
