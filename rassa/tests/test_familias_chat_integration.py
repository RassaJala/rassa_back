"""Tests E2E de integración Familias ↔ Chat (Fases 2-5).

Cubre los flujos del servicio síncrono explícito (ViewSets de Familias) y
la señal de rename, más los endpoints de resincronización y override.

Nota on_commit: Django TestCase envuelve cada test en una transacción que se
revierte, por lo que los callbacks ``transaction.on_commit`` NO se ejecutan.
Los servicios explícitos (ensure_family_chat en perform_create, etc.) sí corren
porque están dentro de la atomic del test. La señal rename usa on_commit, así
que esos tests invocan ``chat_sync.sync_family_chat_name`` directamente para
verificar la lógica (el wiring se cubre por smoke import en apps.ready).
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from rassa.blueprints.chat.services import chat_sync
from rassa.models import (
    Conversacion,
    Familia,
    FamiliaUsuario,
    Integrante,
    Mensaje,
    Persona,
    Rol,
    Usuario,
)

User = get_user_model()


def _crear_usuario(username, rol_nombre="Admin"):
    """Crea User + Persona + Rol + Usuario. Rol Admin por defecto (acceso a endpoints de familia)."""
    rol, _ = Rol.objects.get_or_create(
        nombre_rol=rol_nombre,
        defaults={"descripcion": f"Rol de prueba: {rol_nombre}"},
    )
    user = User.objects.create_user(username=username, email=f"{username}@test.com", password="test123")
    persona = Persona.objects.create(
        nombre=username.capitalize(),
        apellido_paterno="Test",
        fecha_nacimiento="1990-01-01",
        sexo="M",
        domicilio="Calle Test",
    )
    usuario, _ = Usuario.objects.get_or_create(
        fk_user=user,
        defaults={
            "fk_persona": persona,
            "telefono": "0000000000",
            "correo": f"{username}@test.com",
            "fk_rol": rol,
        },
    )
    return user, usuario


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {},
        "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
        "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
        "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
        "PAGE_SIZE": 20,
        "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    }
)
class FamiliaChatIntegrationTests(APITestCase):
    def setUp(self):
        self.user1, self.usuario1 = _crear_usuario("fam1")
        self.user2, self.usuario2 = _crear_usuario("fam2")
        self.user3, self.usuario3 = _crear_usuario("fam3")
        # user1 es el admin que opera los endpoints de Familias.
        self.client.force_authenticate(self.user1)

    # ── helpers ────────────────────────────────────────────────────

    def _crear_familia_api(self, nombre="Familia Test", jefe=None, miembros=None):
        """Crea una familia vía API y la devuelve desde la BD."""
        url = reverse("familia-list")
        payload = {"nombre_familia": nombre}
        if jefe is not None:
            payload["fk_jefe_familia"] = jefe.id_usuario
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        familia = Familia.objects.get(nombre_familia=nombre)
        miembros = miembros if miembros is not None else []
        for u in miembros:
            FamiliaUsuario.objects.get_or_create(fk_usuario=u, fk_familia=familia, defaults={"estado": True})
        # Reconciliación de integrantes/roles tras añadir miembros por ORM.
        chat_sync.ensure_family_chat(familia.id_familia)
        return familia

    # 1. Crear familia crea conversación familiar.
    def test_crear_familia_crea_conversacion_familiar(self):
        url = reverse("familia-list")
        response = self.client.post(url, {"nombre_familia": "Familia Test"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        familia = Familia.objects.get(nombre_familia="Familia Test")
        conv = Conversacion.objects.filter(fk_familia=familia, tipo=True, estado=True).first()
        self.assertIsNotNone(conv)

    # 2. Agregar miembro a la familia agrega integrante al chat.
    def test_agregar_miembro_familia_agrega_integrante_chat(self):
        familia = self._crear_familia_api()
        url = reverse("familia-miembro-list")
        response = self.client.post(
            url,
            {"fk_usuario": self.usuario2.id_usuario, "fk_familia": familia.id_familia},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        conv = Conversacion.objects.get(fk_familia=familia, estado=True)
        integrante = Integrante.objects.get(fk_usuario=self.usuario2, fk_conversacion=conv)
        self.assertTrue(integrante.estado)
        self.assertEqual(integrante.rol, "miembro")

    # 3. Remover miembro de la familia desactiva integrante del chat (mensajes conservados).
    def test_remover_miembro_familia_desactiva_integrante_chat(self):
        familia = self._crear_familia_api(miembros=[self.usuario1, self.usuario2])
        fu = FamiliaUsuario.objects.get(fk_usuario=self.usuario2, fk_familia=familia)
        conv = Conversacion.objects.get(fk_familia=familia, estado=True)
        mensaje = Mensaje.objects.create(fk_emisor=self.usuario2, fk_conversacion=conv, contenido="hola")

        url = reverse("familia-miembro-detail", args=[fu.id_familia_usuario])
        response = self.client.delete(url)
        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT), response.content)

        integrante = Integrante.objects.get(fk_usuario=self.usuario2, fk_conversacion=conv)
        self.assertFalse(integrante.estado)
        self.assertTrue(Mensaje.objects.filter(pk=mensaje.id_mensaje).exists())

    # 4. Renombrar familia sincroniza nombre del chat (señal on_commit → invocamos sync directa).
    def test_renombrar_familia_sincroniza_nombre_chat(self):
        familia = self._crear_familia_api(nombre="Fam Original")
        # on_commit no corre en TestCase: invocamos la sync que la señal dispararía.
        Familia.objects.filter(pk=familia.pk).update(nombre_familia="Nuevo Nombre")
        chat_sync.sync_family_chat_name(familia.pk, "Nuevo Nombre")
        conv = Conversacion.objects.get(fk_familia=familia)
        self.assertEqual(conv.nombre, "Nuevo Nombre")

    # 5. Rename con override no sincroniza.
    def test_rename_familia_con_override_no_sincroniza(self):
        familia = self._crear_familia_api(nombre="Fam Override")
        conv = Conversacion.objects.get(fk_familia=familia)
        conv.nombre_override = True
        conv.save(update_fields=["nombre_override"])
        chat_sync.sync_family_chat_name(familia.pk, "Otro Nombre")
        conv.refresh_from_db()
        self.assertEqual(conv.nombre, "Fam Override")

    # 6. Soft-delete familia archiva el chat (conv + integrantes estado=False).
    def test_soft_delete_familia_archiva_chat(self):
        familia = self._crear_familia_api(miembros=[self.usuario1, self.usuario2])
        conv = Conversacion.objects.get(fk_familia=familia, estado=True)
        Integrante.objects.filter(fk_conversacion=conv).update(estado=True)

        url = reverse("familia-detail", args=[familia.id_familia])
        response = self.client.delete(url)
        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT), response.content)

        conv.refresh_from_db()
        self.assertFalse(conv.estado)
        self.assertFalse(Integrante.objects.filter(fk_conversacion=conv, estado=True).exists())

    # 7. Restore familia reactiva el chat (jefe queda admin).
    def test_restore_familia_reactiva_chat(self):
        familia = self._crear_familia_api(jefe=self.usuario1, miembros=[self.usuario1, self.usuario2])
        # Soft-delete primero
        url_del = reverse("familia-detail", args=[familia.id_familia])
        self.client.delete(url_del)

        url_restore = reverse("familia-restore", args=[familia.id_familia])
        response = self.client.post(url_restore, {"fk_jefe_familia": self.usuario1.id_usuario}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)

        conv = Conversacion.objects.get(fk_familia=familia)
        self.assertTrue(conv.estado)
        jefe_int = Integrante.objects.get(fk_usuario=self.usuario1, fk_conversacion=conv)
        self.assertTrue(jefe_int.estado)
        self.assertEqual(jefe_int.rol, "admin")

    # 8. Permanent familia archiva chat (la conv sobrevive con estado=False y fk_familia=None).
    def test_permanent_familia_archiva_chat(self):
        familia = self._crear_familia_api(miembros=[self.usuario1])
        conv = Conversacion.objects.get(fk_familia=familia, estado=True)
        # Permanent actúa sobre familias ya soft-deleteadas (get_queryset filtra estado=False).
        Familia.objects.filter(pk=familia.pk).update(estado=False)

        url = reverse("familia-permanent", args=[familia.id_familia])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)

        conv.refresh_from_db()
        self.assertFalse(conv.estado)
        self.assertIsNone(conv.fk_familia_id)

    # 9. Asignar jefe actualiza el rol del integrante en el chat.
    def test_asignar_jefe_actualiza_rol_chat(self):
        familia = self._crear_familia_api(miembros=[self.usuario1, self.usuario2, self.usuario3])
        url = reverse("familia-asignar-jefe", args=[familia.id_familia])
        response = self.client.post(url, {"fk_jefe_familia": self.usuario2.id_usuario}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)

        conv = Conversacion.objects.get(fk_familia=familia, estado=True)
        self.assertEqual(Integrante.objects.get(fk_usuario=self.usuario2, fk_conversacion=conv).rol, "admin")
        self.assertEqual(Integrante.objects.get(fk_usuario=self.usuario3, fk_conversacion=conv).rol, "miembro")

    # 10. Endpoint de resincronización reactiva/crea la conversación familiar.
    def test_endpoint_resincronizar_chat_familia(self):
        familia = self._crear_familia_api()
        # Desactivar manualmente la conv
        conv = Conversacion.objects.get(fk_familia=familia, estado=True)
        chat_sync.deactivate_family_chat(familia.id_familia)

        url = reverse("chat-conversaciones-familia-sincronizar", args=[familia.id_familia])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertEqual(response.json()["data"]["id_familia"], familia.id_familia)
        # ensure_family_chat sobre conv inactiva busca estado=True → no la reactiva, crea nueva.
        self.assertEqual(Conversacion.objects.filter(fk_familia=familia, estado=True).count(), 1)

    # 11. Endpoint override-nombre toggle habilita/deshabilita rename.
    def test_endpoint_override_nombre_toggle(self):
        familia = self._crear_familia_api(miembros=[self.usuario1])
        familia.fk_jefe_familia = self.usuario1
        familia.save(update_fields=["fk_jefe_familia"])
        conv = chat_sync.ensure_family_chat(familia.id_familia)

        url = reverse("chat-conversaciones-override-nombre", args=[conv.id_conversacion])
        response = self.client.patch(url, {"nombre_override": True}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        conv.refresh_from_db()
        self.assertTrue(conv.nombre_override)

        # Con override=True el rename via endpoint está permitido.
        url_rename = reverse("chat-conversaciones-renombrar", args=[conv.id_conversacion])
        r_rename = self.client.patch(url_rename, {"nombre": "Custom"}, format="json")
        self.assertEqual(r_rename.status_code, status.HTTP_200_OK)

        # Toggle a False bloquea el rename de nuevo.
        response = self.client.patch(url, {"nombre_override": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        conv.refresh_from_db()
        self.assertFalse(conv.nombre_override)
        r_blocked = self.client.patch(url_rename, {"nombre": "Bloqueado"}, format="json")
        self.assertEqual(r_blocked.status_code, status.HTTP_400_BAD_REQUEST)

    # 12. Remover al jefe de familia actualiza los roles del chat: el jefe removido
    # ya no es admin y, si no hay nuevo jefe, ningún integrante activo queda admin.
    def test_remover_jefe_familia_actualiza_roles_chat(self):
        familia = self._crear_familia_api(miembros=[self.usuario1, self.usuario2])
        familia.fk_jefe_familia = self.usuario1
        familia.save(update_fields=["fk_jefe_familia"])
        conv = chat_sync.ensure_family_chat(familia.id_familia)

        self.assertEqual(
            Integrante.objects.get(fk_usuario=self.usuario1, fk_conversacion=conv).rol,
            "admin",
        )
        self.assertEqual(
            Integrante.objects.get(fk_usuario=self.usuario2, fk_conversacion=conv).rol,
            "miembro",
        )

        fu = FamiliaUsuario.objects.get(fk_usuario=self.usuario1, fk_familia=familia)
        url = reverse("familia-miembro-detail", args=[fu.id_familia_usuario])
        response = self.client.delete(url)
        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT), response.content)

        familia.refresh_from_db()
        self.assertIsNone(familia.fk_jefe_familia)

        jefe_removido = Integrante.objects.get(fk_usuario=self.usuario1, fk_conversacion=conv)
        self.assertFalse(jefe_removido.estado)
        self.assertEqual(jefe_removido.rol, "miembro")

        restante = Integrante.objects.get(fk_usuario=self.usuario2, fk_conversacion=conv)
        self.assertTrue(restante.estado)
        self.assertEqual(restante.rol, "miembro")
        self.assertFalse(Integrante.objects.filter(fk_conversacion=conv, estado=True, rol="admin").exists())

    # 13. test_crear_grupal_rechaza_fk_familia ya existe en Fase 1 — no duplicar.

    # 13. Constraint unique_active_family_conversation vía API/ORM.
    def test_unique_active_family_conversation_via_api(self):
        familia = self._crear_familia_api()  # crea 1 conv activa
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Conversacion.objects.create(tipo=True, fk_familia=familia, estado=True)
