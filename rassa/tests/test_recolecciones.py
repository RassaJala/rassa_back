"""Pruebas unitarias para el módulo de Recolecciones."""

import threading
from datetime import timedelta
from unittest import skipUnless

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from rassa.blueprints.recoleccion.serializers import MSG_AGRICULTOR_NO_EXISTE_O_INACTIVO
from rassa.models import HistorialEstadoRecoleccion, Persona, Recoleccion, Rol, Usuario

# Fechas dinámicas relativas a hoy: evitan la "bomba de tiempo" del guard de
# fechas pasadas (el CI se rompería cuando una fecha fija quedara atrás).
# Margen amplio (7/8 días) a propósito: estas constantes se calculan al importar
# el módulo y una suite que corra en el mismo proceso cruzando 2+ medianoches
# rompería con +1 día. Los tests solo necesitan "una fecha futura/pasada", no
# "mañana/ayer" exactos; los que requieren hoy usan timezone.localdate() directo.
FECHA_FUTURA = timezone.localdate() + timedelta(days=7)
FECHA_FUTURA_2 = timezone.localdate() + timedelta(days=8)
FECHA_PASADA = timezone.localdate() - timedelta(days=7)


def _crear_usuario(username, correo, nombre, apellido, rol):
    """Helper compartido: crea User + Persona + Usuario para los tests del módulo."""
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
        return _crear_usuario(username, correo, nombre, apellido, rol)

    def _payload(self, fecha=str(FECHA_FUTURA)):
        return {
            "fk_agricultor": self.usuario_agricultor.id_usuario,
            "fecha_recoleccion": fecha,
            "hora_inicio": "08:00:00",
            "hora_fin": "11:00:00",
            "comentarios": "Recolección semanal de hortalizas",
        }

    def _crear_recoleccion(self, **kwargs):
        datos = {"fk_agricultor": self.usuario_agricultor, "fecha_recoleccion": FECHA_FUTURA}
        datos.update(kwargs)
        return Recoleccion.objects.create(**datos)

    def test_crear_recoleccion_exito(self):
        """Valida la creación exitosa de una recolección con estado por defecto."""
        response = self.client.post("/api/recolecciones/", self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["data"]["estado"], "pendiente")
        self.assertEqual(Recoleccion.objects.count(), 1)
        recoleccion = Recoleccion.objects.get()
        historial = HistorialEstadoRecoleccion.objects.get(fk_recoleccion=recoleccion)
        self.assertIsNone(historial.estado_anterior)
        self.assertEqual(historial.estado_nuevo, "pendiente")

    def test_crear_rollback_si_falla_el_historial(self):
        """Valida que la transacción revierta si falla el registro del historial."""
        from unittest import mock

        self.client.raise_request_exception = False
        with mock.patch(
            "rassa.blueprints.recoleccion.views.HistorialEstadoRecoleccion.objects.create",
            side_effect=Exception("boom"),
        ):
            response = self.client.post("/api/recolecciones/", self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(Recoleccion.objects.count(), 0)
        self.assertEqual(HistorialEstadoRecoleccion.objects.count(), 0)

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
        response = self.client.post("/api/recolecciones/", self._payload(fecha=str(FECHA_FUTURA_2)), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_crear_mismo_agricultor_fecha_despues_cancelar(self):
        """Valida que se pueda reprogramar la misma fecha tras cancelar la recolección previa."""
        recoleccion = self._crear_recoleccion()
        response_cancel = self.client.post(f"/api/recolecciones/{recoleccion.pk}/cancelar/", format="json")
        self.assertEqual(response_cancel.status_code, status.HTTP_200_OK)
        response = self.client.post("/api/recolecciones/", self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_slot_ocupado_tras_recolectar(self):
        """Fija la regla de negocio: una recolección recolectada SIGUE ocupando el slot
        agricultor+fecha; no se puede programar otra activa ese mismo día."""
        # Fecha = hoy a propósito: en_ruta -> recolectado solo se permite a partir
        # del día de la cita (regla de completado anticipado).
        recoleccion = self._crear_recoleccion(fecha_recoleccion=str(timezone.localdate()))
        response_en_ruta = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "en_ruta"}, format="json"
        )
        self.assertEqual(response_en_ruta.status_code, status.HTTP_200_OK)
        response_recolectado = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "recolectado"}, format="json"
        )
        self.assertEqual(response_recolectado.status_code, status.HTTP_200_OK)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.estado, "recolectado")
        response = self.client.post(
            "/api/recolecciones/", self._payload(fecha=str(timezone.localdate())), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_agricultor", response.data)

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
        self._crear_recoleccion(fecha_recoleccion=str(FECHA_FUTURA_2), estado="en_ruta")
        response = self.client.get("/api/recolecciones/", {"estado": "pendiente"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]["results"]), 1)
        self.assertEqual(response.data["data"]["results"][0]["estado"], "pendiente")

    def test_listar_con_filtro_agricultor_y_fecha(self):
        """Valida el filtrado combinado por agricultor y fecha."""
        self._crear_recoleccion()
        self._crear_recoleccion(fecha_recoleccion=str(FECHA_FUTURA_2))
        response = self.client.get(
            "/api/recolecciones/",
            {
                "fk_agricultor": self.usuario_agricultor.id_usuario,
                "fecha": str(FECHA_FUTURA),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]["results"]), 1)
        self.assertEqual(response.data["data"]["results"][0]["fecha_recoleccion"], str(FECHA_FUTURA))

    def test_detalle_recoleccion(self):
        """Valida el detalle de una recolección con el nombre del agricultor."""
        recoleccion = self._crear_recoleccion()
        response = self.client.get(f"/api/recolecciones/{recoleccion.pk}/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["agricultor_nombre"], "Agricultor Rassa")

    def test_detalle_ignora_filtros_invalidos(self):
        """Valida que los query params de filtro NO afecten el detalle (retrieve).

        Antes, get_queryset corría _aplicar_filtros en retrieve: ?estado=zzz daba
        400 y ?fecha=invalida rompía un detalle que existe. Los filtros solo
        aplican al listado (list).
        """
        recoleccion = self._crear_recoleccion()
        response = self.client.get(f"/api/recolecciones/{recoleccion.pk}/?estado=zzz", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(f"/api/recolecciones/{recoleccion.pk}/?fecha=2026-13-99", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(
            f"/api/recolecciones/{recoleccion.pk}/?fk_agricultor=99999999999999999999", format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

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
        # Fecha = hoy: en_ruta -> recolectado antes de la fecha programada se bloquea.
        recoleccion = self._crear_recoleccion(fecha_recoleccion=str(timezone.localdate()))
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
        """Valida que un pendiente con fecha FUTURA no salte directo a recolectado (debe ir por en_ruta)."""
        recoleccion = self._crear_recoleccion()
        response = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "recolectado"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.estado, "pendiente")

    def test_cambiar_estado_pendiente_a_cancelado(self):
        """Valida la transición pendiente -> cancelado vía /estado/ (solo /cancelar/ estaba cubierto)."""
        recoleccion = self._crear_recoleccion()
        response = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "cancelado"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.estado, "cancelado")

    def test_pendiente_vencido_puede_recolectarse_directo(self):
        """Valida el completado tardío directo: un pendiente vencido puede marcarse recolectado."""
        recoleccion = self._crear_recoleccion(fecha_recoleccion=str(FECHA_PASADA))
        response = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "recolectado"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.estado, "recolectado")

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
        self._crear_recoleccion(fecha_recoleccion=str(FECHA_FUTURA_2))
        response = self.client.get("/api/recolecciones/", {"fecha_desde": str(FECHA_FUTURA_2)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["data"]["results"]), 1)
        self.assertEqual(response.data["data"]["results"][0]["fecha_recoleccion"], str(FECHA_FUTURA_2))

        response = self.client.get(
            "/api/recolecciones/",
            {"fecha_desde": str(FECHA_FUTURA_2), "fecha_hasta": str(FECHA_FUTURA)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_listado_orden_estable_con_horas_null(self):
        """Valida el tiebreaker de paginación: misma fecha y horas NULL ordenan por id.

        Sin el orden secundario por id_recoleccion, dos filas con la misma clave
        de orden primaria (fecha + hora NULL) dejarían un orden indeterminado
        que salta/duplica filas entre páginas cuando el dataset cambia.
        """
        otros = [
            self._crear_usuario(f"agri_tie_{i}", f"tie{i}@rassa.com", "Tie", "Rassa", self.rol_agricultor)
            for i in range(3)
        ]
        r1 = self._crear_recoleccion(fk_agricultor=otros[0], fecha_recoleccion=str(FECHA_FUTURA))
        r2 = self._crear_recoleccion(fk_agricultor=otros[1], fecha_recoleccion=str(FECHA_FUTURA))
        r3 = self._crear_recoleccion(fk_agricultor=otros[2], fecha_recoleccion=str(FECHA_FUTURA))
        response = self.client.get("/api/recolecciones/", {"fecha": str(FECHA_FUTURA)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["id_recoleccion"] for item in response.data["data"]["results"]]
        self.assertEqual(ids, sorted([r1.pk, r2.pk, r3.pk]))

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

    def test_crear_agricultor_nulo_mensaje_espanol(self):
        """Contrato Spanish: fk_agricultor null -> "El agricultor es obligatorio." y no inglés."""
        payload = self._payload()
        payload["fk_agricultor"] = None
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["fk_agricultor"][0], "El agricultor es obligatorio.")

    def test_crear_agricultor_inexistente_mensaje_espanol(self):
        """Contrato Spanish: pk válida inexistente -> MSG_AGRICULTOR_NO_EXISTE_O_INACTIVO y no inglés."""
        payload = self._payload()
        payload["fk_agricultor"] = 99999
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["fk_agricultor"][0], MSG_AGRICULTOR_NO_EXISTE_O_INACTIVO)

    def test_estado_invalido_en_estado_mensaje_espanol(self):
        """Contrato Spanish: /estado/ con estado inválido -> mensaje con los valores válidos, no inglés."""
        recoleccion = self._crear_recoleccion()
        response = self.client.post(f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "zzz"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Estado inválido", str(response.data["estado"][0]))
        self.assertIn("pendiente", str(response.data["estado"][0]))

    def test_crear_con_agricultor_sin_rol(self):
        """Valida que falle la creación con un usuario que no tiene rol Agricultor."""
        payload = self._payload()
        payload["fk_agricultor"] = self.usuario_cliente.id_usuario
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_agricultor", response.data)

    def test_crear_fk_agricultor_fuera_de_rango_retorna_400(self):
        """Valida que un fk_agricultor fuera de rango en el body retorne 400 y no 500.

        La pre-validación de la vista (_pk_entero_valido) corre ANTES de que el
        serializer toque la BD: en Postgres, sin el guard, Usuario.objects.get(pk=<gigante>)
        lanza NumericValueOutOfRange (DataError) que DRF no convierte -> 500. SQLite
        no valida rangos, por eso la suite no lo detectaba antes del fix.
        """
        payload = self._payload()
        payload["fk_agricultor"] = 99999999999999999999
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_agricultor", response.data)
        self.assertIn("número entero válido", str(response.data))

    def test_crear_fk_agricultor_digito_unicode_retorna_400(self):
        """Valida que un dígito Unicode (ej. '٥') en fk_agricultor no cause 500.

        str('٥').isdigit() es True pero int('٥') lanza ValueError; el guard usa
        isascii() para excluirlo y devolver 400.
        """
        payload = self._payload()
        payload["fk_agricultor"] = "٥"
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_agricultor", response.data)

    def test_crear_body_lista_retorna_400(self):
        """Valida que un body JSON array en create no cause 500 por .get() sobre lista."""
        response = self.client.post("/api/recolecciones/", ["fk_agricultor"], format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_body_lista_retorna_400(self):
        """Valida que un body JSON array en partial_update no cause 500 (mismo guard que create)."""
        response = self.client.patch("/api/recolecciones/1/", ["fk_agricultor"], format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_crear_fk_agricultor_digitos_excesivos_retorna_400(self):
        """Valida que un fk_agricultor de >4300 dígitos no cause 500.

        Python 3.12 limita la conversión int<->str a 4300 dígitos
        (sys.set_int_max_str_digits); sin el try/except, int('9'*5001) lanza
        ValueError no capturado -> 500. El guard lo devuelve como 400.
        """
        payload = self._payload()
        payload["fk_agricultor"] = "9" * 5001
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_agricultor", response.data)

    def test_patch_fk_agricultor_fuera_de_rango_retorna_400(self):
        """Valida que un fk_agricultor fuera de rango en PATCH retorne 400 y no 500."""
        recoleccion = self._crear_recoleccion()
        response = self.client.patch(
            f"/api/recolecciones/{recoleccion.pk}/",
            {"fk_agricultor": 99999999999999999999},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_agricultor", response.data)
        self.assertIn("número entero válido", str(response.data))

    def test_patch_duplicado_misma_fecha(self):
        """Valida que no se pueda mover una recolección a una fecha con recolección activa."""
        self._crear_recoleccion()
        recoleccion = self._crear_recoleccion(fecha_recoleccion=str(FECHA_FUTURA_2))
        response = self.client.patch(
            f"/api/recolecciones/{recoleccion.pk}/",
            {"fecha_recoleccion": str(FECHA_FUTURA)},
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

    def test_create_con_solo_hora_inicio_retorna_400(self):
        """Valida la regla both-or-none: no se puede enviar solo hora_inicio."""
        payload = self._payload()
        del payload["hora_fin"]
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_fin", response.data)

    def test_create_con_solo_hora_fin_retorna_400(self):
        """Valida la regla both-or-none: no se puede enviar solo hora_fin."""
        payload = self._payload()
        del payload["hora_inicio"]
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_fin", response.data)

    def test_create_con_ambas_horas_ok(self):
        """Valida que enviar ambas horas sea válido."""
        response = self.client.post("/api/recolecciones/", self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_sin_horas_ok(self):
        """Valida que las horas sean opcionales: sin ninguna se crea la recolección."""
        payload = self._payload()
        del payload["hora_inicio"]
        del payload["hora_fin"]
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_hora_inicio_null_sin_hora_fin_retorna_400(self):
        """Valida el contrato both-or-none por PRESENCIA de claves (XOR).

        POST {"hora_inicio": null} sin hora_fin es un par 'tocado' -> 400.
        Antes se validaba por bool() y un null explícito se aceptaba en silencio
        (bool(None) == bool(None)), asimétrico con el PATCH que sí daba 400.
        """
        payload = self._payload()
        payload["hora_inicio"] = None
        del payload["hora_fin"]
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_fin", response.data)

    def test_create_hora_fin_null_con_hora_inicio_valida_retorna_400(self):
        """Valida el hueco del XOR: ambas claves presentes pero una null.

        POST {"hora_inicio": "08:00:00", "hora_fin": null} pasa el XOR de presencia
        (ambas claves presentes) pero deja el par efectivo incompleto; el chequeo de
        valores (bool) lo rechaza -> 400 y no persiste un par incompleto en BD.
        """
        payload = self._payload()
        payload["hora_fin"] = None
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_fin", response.data)

    def test_patch_par_de_horas_incompleto_retorna_400(self):
        """Valida que PATCH no pueda dejar el par de horas incompleto."""
        recoleccion = self._crear_recoleccion()
        response = self.client.patch(
            f"/api/recolecciones/{recoleccion.pk}/",
            {"hora_inicio": "08:00:00"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_fin", response.data)

    def test_patch_campos_ajenos_sobre_par_incompleto_legacy_ok(self):
        """Valida que PATCH de campos ajenos (no horas) no falle sobre una fila legacy
        con par de horas incompleto (solo hora_inicio): la regla both-or-none solo
        aplica cuando el cliente toca las horas."""
        recoleccion = self._crear_recoleccion(hora_inicio="07:00:00", hora_fin=None)
        response = self.client.patch(
            f"/api/recolecciones/{recoleccion.pk}/",
            {"comentarios": "Recolección reprogramada"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.comentarios, "Recolección reprogramada")
        self.assertEqual(recoleccion.hora_inicio.isoformat(), "07:00:00")
        self.assertIsNone(recoleccion.hora_fin)

    def test_patch_hora_inicio_null_explicito_retorna_400(self):
        """Valida que PATCH con hora_inicio null explícito no deje un par incompleto
        (bypass de la regla both-or-none): null enviado es una hora 'tocada'."""
        recoleccion = self._crear_recoleccion(hora_inicio="08:00:00", hora_fin="11:00:00")
        response = self.client.patch(
            f"/api/recolecciones/{recoleccion.pk}/",
            {"hora_inicio": None},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_fin", response.data)
        recoleccion.refresh_from_db()
        # El par original no se alteró (el save nunca llegó a ejecutarse).
        self.assertEqual(recoleccion.hora_inicio.isoformat(), "08:00:00")
        self.assertEqual(recoleccion.hora_fin.isoformat(), "11:00:00")

    def test_patch_hora_fin_null_explicito_retorna_400(self):
        """Valida que PATCH con hora_fin null explícito no deje un par incompleto."""
        recoleccion = self._crear_recoleccion(hora_inicio="08:00:00", hora_fin="11:00:00")
        response = self.client.patch(
            f"/api/recolecciones/{recoleccion.pk}/",
            {"hora_fin": None},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_fin", response.data)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.hora_inicio.isoformat(), "08:00:00")
        self.assertEqual(recoleccion.hora_fin.isoformat(), "11:00:00")

    def test_fecha_pasada_retorna_400(self):
        """Valida que no se pueda programar una recolección en una fecha pasada."""
        payload = self._payload(fecha=str(FECHA_PASADA))
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fecha_recoleccion", response.data)

    def test_patch_recoleccion_con_fecha_pasada_no_bloqueado(self):
        """Valida que editar campos (no la fecha) de una recolección con fecha pasada no se bloquee."""
        recoleccion = self._crear_recoleccion(fecha_recoleccion=str(FECHA_PASADA))
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
            {"fecha_recoleccion": str(FECHA_PASADA)},
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

    def test_pendiente_fecha_hoy_puede_pasar_a_en_ruta(self):
        """Valida que una recolección programada para HOY pueda pasar a en_ruta.

        El guard de fecha pasada usa < (estrictamente anterior), no <=: una cita
        de hoy está dentro de la ventana permitida para iniciar el traslado.
        """
        recoleccion = self._crear_recoleccion(fecha_recoleccion=str(timezone.localdate()))
        response = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "en_ruta"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.estado, "en_ruta")

    def test_en_ruta_fecha_pasada_puede_cancelar(self):
        """Valida que una recolección en ruta con fecha pasada pueda cancelarse.

        Cancelar desde en_ruta está permitido por diseño independientemente de la
        fecha (el guard de fecha pasada solo bloquea pendiente -> en_ruta).
        """
        recoleccion = self._crear_recoleccion(fecha_recoleccion=str(FECHA_PASADA), estado="en_ruta")
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

    def test_usuario_con_fk_rol_none_recibe_403_no_500(self):
        """Valida que un perfil Usuario sin rol (fk_rol=None) reciba 403 y no 500.

        Reproduce el perfil legacy/roto: HasRole delegaba en tiene_rol() que
        accedía a fk_rol.nombre_rol y explotaba con AttributeError -> 500 en TODO
        endpoint protegido. Con el fix null-safe se deniega limpio (403).
        """
        # Perfil con fk_rol=None en memoria (la columna es NOT NULL en BD; el
        # escenario se reproduce con el perfil "detachado" que cachea el request).
        self.usuario_vendedor.fk_rol = None
        self.usuario_vendedor.fk_user.usuario = self.usuario_vendedor
        self.client.force_authenticate(user=self.usuario_vendedor.fk_user)
        response = self.client.post("/api/recolecciones/", self._payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_hora_fin_tras_hora_inicio(self):
        """Valida la comparación de horas (hora_fin > hora_inicio) también en PATCH."""
        recoleccion = self._crear_recoleccion(hora_inicio="08:00:00")
        # Enviar AMBAS claves a propósito: con solo "hora_fin" el serializer
        # falla antes por el par incompleto (XOR de presencia) y el test no
        # ejercitaría la comparación de valores que dice validar.
        response = self.client.patch(
            f"/api/recolecciones/{recoleccion.pk}/",
            {"hora_inicio": "08:00:00", "hora_fin": "07:00:00"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_fin", response.data)

    def test_filtro_fecha_hasta_invalida_retorna_400(self):
        """Valida que un fecha_hasta malformado retorne 400 y no 500."""
        response = self.client.get("/api/recolecciones/", {"fecha_hasta": "2026-13-99"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pk_no_numerico_retorna_404(self):
        """Valida que un pk no numérico retorne 404 en detalle, estado y cancelar."""
        response = self.client.get("/api/recolecciones/abc/", format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.post("/api/recolecciones/abc/estado/", {"estado": "en_ruta"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.post("/api/recolecciones/abc/cancelar/", format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_estado_y_cancelar_recoleccion_inexistente_404(self):
        """Valida que /estado/ y /cancelar/ retornen 404 para una recolección inexistente."""
        response = self.client.post("/api/recolecciones/99999/estado/", {"estado": "en_ruta"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.post("/api/recolecciones/99999/cancelar/", format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_duplicado_path_integrity_error(self):
        """Valida que PATCH que viola el constraint devuelva 400 (path IntegrityError)."""
        from unittest import mock

        from rassa.blueprints.recoleccion.serializers import RecoleccionSerializer

        self._crear_recoleccion()
        recoleccion = self._crear_recoleccion(fecha_recoleccion=str(FECHA_FUTURA_2))
        with mock.patch.object(RecoleccionSerializer, "validate", lambda self, attrs: attrs):
            response = self.client.patch(
                f"/api/recolecciones/{recoleccion.pk}/",
                {"fecha_recoleccion": str(FECHA_FUTURA)},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_agricultor", response.data)

    def test_estado_transicion_fecha_pasada_bloqueada(self):
        """Valida que una recolección con fecha pasada solo pueda cancelarse."""
        recoleccion = self._crear_recoleccion(fecha_recoleccion=str(FECHA_PASADA))
        response = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "en_ruta"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fecha_recoleccion", response.data)

        response = self.client.post(f"/api/recolecciones/{recoleccion.pk}/cancelar/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.estado, "cancelado")

    def test_en_ruta_fecha_pasada_puede_recolectarse(self):
        """Valida que una recolección en ruta con fecha pasada pueda marcarse como recolectada (completado tardío)."""
        recoleccion = self._crear_recoleccion(fecha_recoleccion=str(FECHA_PASADA), estado="en_ruta")
        response = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "recolectado"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.estado, "recolectado")

    def test_en_ruta_fecha_futura_no_puede_recolectarse(self):
        """Regla de negocio (pendiente de confirmación): un en_ruta no puede marcarse
        recolectado ANTES de su fecha programada (una cita futura no se completa hoy)."""
        recoleccion = self._crear_recoleccion(estado="en_ruta")  # fecha FECHA_FUTURA
        response = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "recolectado"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fecha_recoleccion", response.data)
        self.assertIn("antes de su fecha programada", str(response.data["fecha_recoleccion"]))
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.estado, "en_ruta")

    def test_en_ruta_fecha_hoy_puede_recolectarse(self):
        """Regla de negocio: a partir del día de la cita (fecha <= hoy) se permite completar."""
        recoleccion = self._crear_recoleccion(fecha_recoleccion=str(timezone.localdate()), estado="en_ruta")
        response = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "recolectado"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        recoleccion.refresh_from_db()
        self.assertEqual(recoleccion.estado, "recolectado")

    def test_historial_estado_se_registra(self):
        """Valida que cada cambio de estado (estado/cancelar) registre historial."""
        recoleccion = self._crear_recoleccion()
        response = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "en_ruta"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        historial = HistorialEstadoRecoleccion.objects.filter(fk_recoleccion=recoleccion).order_by("id_historial")
        self.assertEqual(historial.count(), 1)
        self.assertEqual(historial.first().estado_anterior, "pendiente")
        self.assertEqual(historial.first().estado_nuevo, "en_ruta")

        response = self.client.post(f"/api/recolecciones/{recoleccion.pk}/cancelar/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        historial = HistorialEstadoRecoleccion.objects.filter(fk_recoleccion=recoleccion).order_by("id_historial")
        self.assertEqual(historial.count(), 2)
        self.assertEqual(historial.last().estado_anterior, "en_ruta")
        self.assertEqual(historial.last().estado_nuevo, "cancelado")

    def test_cancelar_recoleccion_cancelada_idempotente(self):
        """Valida que cancelar una recolección ya cancelada retorne 200 sin nuevo historial."""
        recoleccion = self._crear_recoleccion(estado="cancelado")
        response = self.client.post(f"/api/recolecciones/{recoleccion.pk}/cancelar/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "La recolección ya estaba cancelada.")
        self.assertEqual(HistorialEstadoRecoleccion.objects.filter(fk_recoleccion=recoleccion).count(), 0)

    def test_cambiar_estado_sobre_cancelada_estricto(self):
        """Valida el contraste de contratos: /estado/ es estricto (400 si el estado ya es el pedido),
        a diferencia de /cancelar/ que es idempotente (200)."""
        recoleccion = self._crear_recoleccion(estado="cancelado")
        response = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/", {"estado": "cancelado"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estado", response.data)

    def test_cambiar_estado_rechaza_campos_extra(self):
        """Valida que /estado/ rechace campos adicionales al body."""
        recoleccion = self._crear_recoleccion()
        response = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/",
            {"estado": "en_ruta", "comentarios": "no permitido"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estado", response.data)

    def test_estado_body_no_dict_retorna_400(self):
        """Valida que /estado/ rechace un body que no sea objeto JSON (lista) con 400 y no 500."""
        recoleccion = self._crear_recoleccion()
        response = self.client.post(
            f"/api/recolecciones/{recoleccion.pk}/estado/",
            ["en_ruta"],
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estado", response.data)

    def test_crear_dataerror_no_se_convierte_en_500(self):
        """Valida que un fk_agricultor fuera de rango no llegue nunca al get(pk=...).

        El guard de la vista (_pk_entero_valido) rechaza el valor ANTES de que el
        serializer toque la BD, en ambos motores: en Postgres un get(pk=<gigante>)
        lanzaría NumericValueOutOfRange (DataError) que DRF no convierte -> 500;
        en SQLite pasa por does_not_exist. El fix cubre ambos por igual.
        """
        payload = self._payload()
        payload["fk_agricultor"] = 2**31  # justo fuera del rango de AutoField
        response = self.client.post("/api/recolecciones/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_agricultor", response.data)
        self.assertIn("número entero válido", str(response.data))

    def test_listar_autenticado_sin_perfil_usuario_retorna_403(self):
        """Valida que un User sin perfil Usuario reciba 403 explícito al listar (no 200 vacío)."""
        user_huertano = User.objects.create_user(username="huertano", password="password123")
        self.client.force_authenticate(user=user_huertano)
        response = self.client.get("/api/recolecciones/", format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("perfil", str(response.data))

    def test_agricultor_puede_listar_sus_recolecciones(self):
        """Valida que un agricultor liste y vea solo sus propias recolecciones."""
        recoleccion = self._crear_recoleccion()
        usuario_agricultor2 = self._crear_usuario(
            "agricultor2", "agricultor2@rassa.com", "Agricultor2", "Rassa", self.rol_agricultor
        )
        recoleccion_ajena = Recoleccion.objects.create(
            fk_agricultor=usuario_agricultor2,
            fecha_recoleccion=FECHA_FUTURA_2,
        )
        self.client.force_authenticate(user=self.usuario_agricultor.fk_user)

        response = self.client.get("/api/recolecciones/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["id_recoleccion"] for item in response.data["data"]["results"]]
        self.assertIn(recoleccion.pk, ids)
        self.assertNotIn(recoleccion_ajena.pk, ids)

        response = self.client.get(f"/api/recolecciones/{recoleccion.pk}/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(f"/api/recolecciones/{recoleccion_ajena.pk}/", format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_agricultor_filtro_agricultor_ajeno_retorna_400(self):
        """Valida que un agricultor no pueda filtrar por otro agricultor: 400 y no [] silencioso."""
        self._crear_recoleccion()
        usuario_agricultor2 = self._crear_usuario(
            "agricultor3", "agricultor3@rassa.com", "Agricultor3", "Rassa", self.rol_agricultor
        )
        self.client.force_authenticate(user=self.usuario_agricultor.fk_user)
        response = self.client.get(
            "/api/recolecciones/", {"fk_agricultor": usuario_agricultor2.id_usuario}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_agricultor", response.data)

        response = self.client.get(
            "/api/recolecciones/", {"fk_agricultor": self.usuario_agricultor.id_usuario}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_fk_agricultor_filtro_fuera_de_rango_retorna_400(self):
        """Valida que un fk_agricultor fuera de rango en el filtro retorne 400 y no 500."""
        response = self.client.get("/api/recolecciones/", {"fk_agricultor": "99999999999999999999"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_agricultor", response.data)

    def test_agricultor_filtro_propio_con_padding_retorna_200(self):
        """Valida que '007' con id 7 se trate como el propio (comparación numérica, no string)."""
        self._crear_recoleccion()
        self.client.force_authenticate(user=self.usuario_agricultor.fk_user)
        fk_con_padding = str(self.usuario_agricultor.id_usuario).zfill(3)
        response = self.client.get("/api/recolecciones/", {"fk_agricultor": fk_con_padding}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_agricultor_filtro_fuera_de_rango_prioriza_entero_valido(self):
        """Valida que un agricultor con fk_agricultor fuera de rango reciba 'entero válido', no 'solo las suyas'."""
        self._crear_recoleccion()
        self.client.force_authenticate(user=self.usuario_agricultor.fk_user)
        response = self.client.get("/api/recolecciones/", {"fk_agricultor": "99999999999999999999"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_agricultor", response.data)
        self.assertIn("número entero válido", str(response.data))

    def test_pk_fuera_de_rango_retorna_404(self):
        """Valida que un pk fuera de rango retorne 404 y no 500."""
        response = self.client.get("/api/recolecciones/99999999999999999999/", format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.post(
            "/api/recolecciones/99999999999999999999/estado/", {"estado": "en_ruta"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


@skipUnless(connection.vendor == "postgresql", "Lock real solo en Postgres")
class RecoleccionConcurrenciaTests(TransactionTestCase):
    """Concurrencia de creates del MISMO par (fk_agricultor, fecha_recoleccion).

    Best-effort: con un barrier los dos threads suelen solaparse, pero si el
    runner los serializa el resultado sigue siendo válido. Lo que NUNCA debe
    pasar es que ambos devuelvan 201: el lock del agricultor en create (re-check
    bajo select_for_update) + el UniqueConstraint parcial lo impiden en Postgres.
    select_for_update() es no-op en SQLite, por eso esta clase se salta ahí.

    NOTA: TransactionTestCase (no TestCase) porque necesita transacciones reales
    concurrentes; select_for_update() dentro de una transacción de TestCase
    (abierta y no commiteada) haría que el segundo thread vea la BD sin los
    cambios del primero y ambos podrían crear.
    """

    def setUp(self):
        self.rol_admin = Rol.objects.create(nombre_rol="Admin", descripcion="Administrador")
        self.rol_agricultor = Rol.objects.create(nombre_rol="Agricultor", descripcion="Agricultor")
        self.usuario_admin = self._crear_usuario("admin_conc", "admin_conc@rassa.com", "Admin", "Conc", self.rol_admin)
        self.usuario_agricultor = self._crear_usuario(
            "agri_conc", "agri_conc@rassa.com", "Agricultor", "Conc", self.rol_agricultor
        )

    def _crear_usuario(self, username, correo, nombre, apellido, rol):
        return _crear_usuario(username, correo, nombre, apellido, rol)

    def test_create_concurrente_mismo_par_un_solo_201(self):
        NUM_THREADS = 2
        results = []
        barrier = threading.Barrier(NUM_THREADS)
        payload = {
            "fk_agricultor": self.usuario_agricultor.id_usuario,
            "fecha_recoleccion": str(FECHA_FUTURA),
            "hora_inicio": "08:00:00",
            "hora_fin": "11:00:00",
        }

        def crear():
            client = APIClient()
            client.force_authenticate(user=self.usuario_admin.fk_user)
            barrier.wait()
            resp = client.post("/api/recolecciones/", payload, format="json")
            results.append(resp.status_code)

        threads = [threading.Thread(target=crear) for _ in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), NUM_THREADS)
        # Exactamente UNO crea; el otro recibe 400 (duplicado). Dos 201 = regresión.
        self.assertEqual(sum(1 for r in results if r == status.HTTP_201_CREATED), 1)
        self.assertEqual(sum(1 for r in results if r == status.HTTP_400_BAD_REQUEST), 1)
        self.assertEqual(Recoleccion.objects.count(), 1)
