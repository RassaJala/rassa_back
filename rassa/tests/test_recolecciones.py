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

    def test_estado_ignorado_en_create_y_patch(self):
        """Valida que 'estado' no se pueda forzar por POST/PATCH (solo vía /estado/ y /cancelar/)."""
        payload = self._payload()
        payload["estado"] = "recolectado"
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["estado"], "pendiente")

        recoleccion = Recoleccion.objects.get(pk=response.data["data"]["id_recoleccion"])
        patch = self.client.patch(f"/api/recolecciones/{recoleccion.pk}/", {"estado": "cancelado"}, format="json")
        self.assertEqual(patch.status_code, status.HTTP_200_OK)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.estado, "pendiente")

    def test_listar_con_filtro_estado(self):
        """Valida el filtrado por estado en el listado de recolecciones."""
        self._crear_recoleccion()
        self._crear_recoleccion(fecha_recoleccion="2026-08-11", estado="en_ruta")
        response = self.client.get("/api/recolecciones/", {"estado": "pendiente"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["estado"], "pendiente")

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
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["fecha_recoleccion"], "2026-08-10")

    def test_detalle_recoleccion(self):
        """Valida el detalle de una recolección con el nombre del agricultor."""
        recoleccion = self._crear_recoleccion()
        response = self.client.get(f"/api/recolecciones/{recoleccion.pk}/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["agricultor_nombre"], "Agricultor Rassa")

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
        self.assertIn("estado", response.data)

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
