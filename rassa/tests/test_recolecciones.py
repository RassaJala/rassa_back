"""Pruebas unitarias para el módulo de Recolecciones."""

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from rassa.models import Persona, Recoleccion, Rol, Usuario


class RecoleccionesTestCase(TestCase):
    """Caso de prueba para la gestión de Recolecciones."""

    def setUp(self):
        self.client = APIClient()

        # Crear roles necesarios
        self.rol_admin = Rol.objects.create(nombre_rol="Admin", descripcion="Administrador")
        self.rol_vendedor = Rol.objects.create(nombre_rol="Vendedor", descripcion="Vendedor")
        self.rol_agricultor = Rol.objects.create(nombre_rol="Agricultor", descripcion="Agricultor")
        self.rol_cliente = Rol.objects.create(nombre_rol="Cliente", descripcion="Cliente")

        # Crear personas y usuarios de prueba
        self.usuario_admin = self._crear_usuario("admin", "admin@rassa.com", "Admin", "Rassa", self.rol_admin)
        self.usuario_vendedor = self._crear_usuario(
            "vendedor", "vendedor@rassa.com", "Vendedor", "Rassa", self.rol_vendedor
        )
        self.usuario_agricultor = self._crear_usuario(
            "agricultor", "agricultor@rassa.com", "Agricultor", "Rassa", self.rol_agricultor
        )
        self.usuario_cliente = self._crear_usuario("cliente", "cliente@rassa.com", "Cliente", "Rassa", self.rol_cliente)

        # Autenticar como Admin por defecto
        self.client.force_authenticate(user=self.usuario_admin.fk_user)

    def _crear_usuario(self, username, correo, nombre, apellido, rol):
        user = User.objects.create_user(username=username, email=correo, password="password123")
        persona = Persona.objects.create(
            nombre=nombre,
            apellido_paterno=apellido,
            fecha_nacimiento="1990-01-01",
            sexo="M",
            domicilio="Calle de prueba 123",
        )
        return Usuario.objects.create(
            fk_user=user,
            fk_persona=persona,
            telefono="1234567890",
            correo=correo,
            fk_rol=rol,
        )

    def _payload(self, fecha="2026-08-10"):
        return {
            "fk_agricultor": self.usuario_agricultor.id_usuario,
            "fecha_recoleccion": fecha,
            "hora_inicio": "08:00:00",
            "hora_fin": "11:00:00",
            "comentarios": "Recolección semanal de hortalizas",
        }

    def _crear_recoleccion(self, **kwargs):
        datos = {"fk_agricultor": self.usuario_agricultor, "fecha_recoleccion": "2026-08-10"}
        datos.update(kwargs)
        return Recoleccion.objects.create(**datos)

    def test_crear_recoleccion_exito(self):
        """Valida la creación exitosa de una recolección con estado por defecto."""
        response = self.client.post("/api/recolecciones/", self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["data"]["estado"], "pendiente")
        self.assertEqual(Recoleccion.objects.count(), 1)

    def test_crear_sin_autenticacion(self):
        """Valida que un request sin autenticación retorne 401."""
        self.client.force_authenticate(user=None)
        response = self.client.post("/api/recolecciones/", self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_crear_duplicado_mismo_agricultor_fecha(self):
        """Valida que no se puedan crear dos recolecciones del mismo agricultor en la misma fecha."""
        self.client.post("/api/recolecciones/", self._payload(), format="json")
        response = self.client.post("/api/recolecciones/", self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_agricultor", response.data)
        self.assertEqual(
            response.data["fk_agricultor"][0],
            "El agricultor ya tiene una recolección programada para esta fecha.",
        )

    def test_crear_mismo_agricultor_distinta_fecha(self):
        """Valida que el mismo agricultor pueda tener recolecciones en fechas distintas."""
        self.client.post("/api/recolecciones/", self._payload(), format="json")
        response = self.client.post("/api/recolecciones/", self._payload(fecha="2026-08-11"), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_crear_mismo_agricultor_fecha_despues_cancelar(self):
        """Valida que se pueda reprogramar la misma fecha tras cancelar la recolección previa."""
        recoleccion = self._crear_recoleccion()
        response_cancel = self.client.post(f"/api/recolecciones/{recoleccion.pk}/cancelar/", format="json")
        self.assertEqual(response_cancel.status_code, status.HTTP_200_OK)
        response = self.client.post("/api/recolecciones/", self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_crear_con_agricultor_inactivo(self):
        """Valida que falle la creación si el agricultor está inactivo."""
        self.usuario_agricultor.estado = False
        self.usuario_agricultor.save()
        response = self.client.post("/api/recolecciones/", self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_agricultor", response.data)

    def test_estado_rechazado_en_create_y_patch(self):
        """Valida que 'estado' se rechace por POST/PATCH (solo vía /estado/ y /cancelar/)."""
        payload = self._payload()
        payload["estado"] = "recolectado"
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estado", response.data)

        recoleccion = self._crear_recoleccion()
        patch = self.client.patch(f"/api/recolecciones/{recoleccion.pk}/", {"estado": "cancelado"}, format="json")
        self.assertEqual(patch.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estado", patch.data)

    def test_listar_con_filtro_estado(self):
        """Valida el filtrado por estado en el listado de recolecciones."""
        self._crear_recoleccion()
        self._crear_recoleccion(fecha_recoleccion="2026-08-11", estado="en_ruta")
        response = self.client.get("/api/recolecciones/", {"estado": "pendiente"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]["results"]), 1)
        self.assertEqual(response.data["data"]["results"][0]["estado"], "pendiente")

    def test_listar_con_filtro_agricultor_y_fecha(self):
        """Valida el filtrado combinado por agricultor y fecha."""
        self._crear_recoleccion()
        self._crear_recoleccion(fecha_recoleccion="2026-08-11")
        response = self.client.get(
            "/api/recolecciones/",
            {
                "fk_agricultor": self.usuario_agricultor.id_usuario,
                "fecha": "2026-08-10",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]["results"]), 1)
        self.assertEqual(response.data["data"]["results"][0]["fecha_recoleccion"], "2026-08-10")

    def test_detalle_recoleccion(self):
        """Valida el detalle de una recolección con el nombre del agricultor."""
        recoleccion = self._crear_recoleccion()
        response = self.client.get(f"/api/recolecciones/{recoleccion.pk}/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["agricultor_nombre"], "Agricultor Rassa")

    def test_editar_comentarios(self):
        """Valida la edición parcial de los comentarios de una recolección."""
        recoleccion = self._crear_recoleccion()
        response = self.client.patch(
            f"/api/recolecciones/{recoleccion.pk}/",
            {"comentarios": "Ajustar hora de llegada"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["data"]["comentarios"], "Ajustar hora de llegada")

    def test_editar_recoleccion_recolectada_bloqueado(self):
        """Valida que no se pueda editar una recolección ya recolectada."""
        recoleccion = self._crear_recoleccion(estado="recolectado")
        response = self.client.patch(
            f"/api/recolecciones/{recoleccion.pk}/",
            {"comentarios": "Cambio prohibido"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estado", response.data)

    def test_cambiar_estado_transicion_valida(self):
        """Valida las transiciones pendiente -> en_ruta -> recolectado."""
        recoleccion = self._crear_recoleccion()
        response1 = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "en_ruta"}, format="json"
        )
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.estado, "en_ruta")

        response2 = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "recolectado"}, format="json"
        )
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.estado, "recolectado")

    def test_cambiar_estado_transicion_invalida(self):
        """Valida que no se pueda saltar de pendiente a recolectado."""
        recoleccion = self._crear_recoleccion()
        response = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "recolectado"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.estado, "pendiente")

    def test_cambiar_estado_mismo_estado(self):
        """Valida que no se pueda cambiar al estado actual."""
        recoleccion = self._crear_recoleccion()
        response = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "pendiente"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancelar_recoleccion(self):
        """Valida la cancelación lógica de una recolección."""
        recoleccion = self._crear_recoleccion()
        response = self.client.post(f"/api/recolecciones/{recoleccion.pk}/cancelar/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.estado, "cancelado")

    def test_cancelar_recoleccion_recolectada(self):
        """Valida que no se pueda cancelar una recolección ya recolectada."""
        recoleccion = self._crear_recoleccion(estado="recolectado")
        response = self.client.post(f"/api/recolecciones/{recoleccion.pk}/cancelar/", format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", response.data)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.estado, "recolectado")

    def test_vendedor_puede_crear(self):
        """Valida que un vendedor pueda crear recolecciones."""
        self.client.force_authenticate(user=self.usuario_vendedor.fk_user)
        response = self.client.post("/api/recolecciones/", self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_agricultor_no_puede_crear(self):
        """Valida que un agricultor no pueda crear recolecciones (403)."""
        self.client.force_authenticate(user=self.usuario_agricultor.fk_user)
        response = self.client.post("/api/recolecciones/", self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_filtro_fecha_invalida_retorna_400(self):
        """Valida que un parámetro de fecha malformado retorne 400 y no 500."""
        response = self.client.get("/api/recolecciones/", {"fecha": "2026-13-99"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.get("/api/recolecciones/", {"fecha_desde": "2026-13-99"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filtro_fecha_desde_hasta(self):
        """Valida el filtrado por rango de fechas."""
        self._crear_recoleccion()
        self._crear_recoleccion(fecha_recoleccion="2026-08-11")
        response = self.client.get("/api/recolecciones/", {"fecha_desde": "2026-08-11"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]["results"]), 1)
        self.assertEqual(response.data["data"]["results"][0]["fecha_recoleccion"], "2026-08-11")

        response = self.client.get(
            "/api/recolecciones/",
            {"fecha_desde": "2026-08-11", "fecha_hasta": "2026-08-10"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filtro_estado_invalido_retorna_400(self):
        """Valida que un estado inválido retorne 400."""
        response = self.client.get("/api/recolecciones/", {"estado": "zzz"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estado", response.data)

    def test_crear_sin_agricultor_retorna_400(self):
        """Valida que falle la creación sin agricultor o con agricultor nulo."""
        payload = self._payload()
        del payload["fk_agricultor"]
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        payload = self._payload()
        payload["fk_agricultor"] = None
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_agricultor", response.data)

    def test_crear_con_agricultor_inexistente(self):
        """Valida que falle la creación con un agricultor inexistente."""
        payload = self._payload()
        payload["fk_agricultor"] = 99999
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_crear_con_agricultor_sin_rol(self):
        """Valida que falle la creación con un usuario que no tiene rol Agricultor."""
        payload = self._payload()
        payload["fk_agricultor"] = self.usuario_cliente.id_usuario
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_agricultor", response.data)

    def test_patch_duplicado_misma_fecha(self):
        """Valida que no se pueda mover una recolección a una fecha con recolección activa."""
        self._crear_recoleccion()
        recoleccion = self._crear_recoleccion(fecha_recoleccion="2026-08-11")
        response = self.client.patch(
            f"/api/recolecciones/{recoleccion.pk}/",
            {"fecha_recoleccion": "2026-08-10"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_agricultor", response.data)

    def test_editar_recoleccion_en_ruta_bloqueado(self):
        """Valida que no se pueda editar una recolección en ruta."""
        recoleccion = self._crear_recoleccion(estado="en_ruta")
        response = self.client.patch(
            f"/api/recolecciones/{recoleccion.pk}/",
            {"comentarios": "Cambio prohibido"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estado", response.data)

    def test_editar_recoleccion_cancelada_bloqueado(self):
        """Valida que no se pueda editar una recolección cancelada."""
        recoleccion = self._crear_recoleccion(estado="cancelado")
        response = self.client.patch(
            f"/api/recolecciones/{recoleccion.pk}/",
            {"comentarios": "Cambio prohibido"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estado", response.data)

    def test_hora_fin_menor_igual_hora_inicio(self):
        """Valida que hora_fin deba ser posterior a hora_inicio."""
        payload = self._payload()
        payload["hora_inicio"] = "10:00:00"
        payload["hora_fin"] = "09:00:00"
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_fin", response.data)

        payload = self._payload()
        payload["hora_inicio"] = "10:00:00"
        payload["hora_fin"] = "10:00:00"
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_fin", response.data)

    def test_fecha_pasada_retorna_400(self):
        """Valida que no se pueda programar una recolección en una fecha pasada."""
        payload = self._payload(fecha="2020-01-01")
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fecha_recoleccion", response.data)

    def test_patch_recoleccion_con_fecha_pasada_no_bloqueado(self):
        """Valida que editar campos (no la fecha) de una recolección con fecha pasada no se bloquee."""
        recoleccion = self._crear_recoleccion(fecha_recoleccion="2026-07-01")
        response = self.client.patch(
            f"/api/recolecciones/{recoleccion.pk}/",
            {"comentarios": "Ajustar hora de llegada"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["comentarios"], "Ajustar hora de llegada")

    def test_patch_cambiar_fecha_a_pasada_retorna_400(self):
        """Valida que PATCH rechace cambiar la fecha a una pasada."""
        recoleccion = self._crear_recoleccion()
        response = self.client.patch(
            f"/api/recolecciones/{recoleccion.pk}/",
            {"fecha_recoleccion": "2020-01-01"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fecha_recoleccion", response.data)

    def test_cancelar_desde_en_ruta(self):
        """Valida que una recolección en ruta pueda cancelarse."""
        recoleccion = self._crear_recoleccion(estado="en_ruta")
        response = self.client.post(f"/api/recolecciones/{recoleccion.pk}/cancelar/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.estado, "cancelado")

    def test_rbac_estado_y_cancelar(self):
        """Valida permisos sobre /estado/ y /cancelar/: vendedor permite, agricultor no."""
        recoleccion = self._crear_recoleccion()

        self.client.force_authenticate(user=self.usuario_vendedor.fk_user)
        response = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "en_ruta"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.usuario_agricultor.fk_user)
        response = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "recolectado"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(f"/api/recolecciones/{recoleccion.pk}/cancelar/", format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_hora_fin_tras_hora_inicio(self):
        """Valida la validación de horas también en PATCH."""
        recoleccion = self._crear_recoleccion(hora_inicio="08:00:00")
        response = self.client.patch(
            f"/api/recolecciones/{recoleccion.pk}/",
            {"hora_fin": "07:00:00"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_fin", response.data)
