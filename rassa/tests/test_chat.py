"""Tests para el módulo M9 Chat.

Cubre los endpoints cuyos contratos fueron ajustados para el frontend:
- Listar conversaciones (con no_leidos y es_familia)
- Crear conversación privada (alias fk_usuario)
- Crear conversación grupal (validación, reactivación, usuarios faltantes)
- Agregar integrante (alias fk_usuario)
- Enviar mensaje con documento (alias conversacion/documento)
- Paginación de mensajes
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from rassa.blueprints.chat import views
from rassa.blueprints.chat.services import chat_sync
from rassa.models import Conversacion, Documento, Familia, FamiliaUsuario, Integrante, Mensaje, Persona, Rol, Usuario

User = get_user_model()


def _crear_usuario(username, rol_nombre="Cliente"):
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
class ChatTests(APITestCase):
    def setUp(self):
        self.user1, self.usuario1 = _crear_usuario("user1")
        self.user2, self.usuario2 = _crear_usuario("user2")
        self.user3, self.usuario3 = _crear_usuario("user3")
        self.client.force_authenticate(self.user1)

    def _crear_conversacion_privada(self):
        conv = Conversacion.objects.create(tipo=False)
        Integrante.objects.create(fk_usuario=self.usuario1, fk_conversacion=conv)
        Integrante.objects.create(fk_usuario=self.usuario2, fk_conversacion=conv)
        return conv

    def _crear_conversacion_grupal(self):
        conv = Conversacion.objects.create(tipo=True, nombre="Grupo test")
        Integrante.objects.create(fk_usuario=self.usuario1, fk_conversacion=conv, rol="admin")
        Integrante.objects.create(fk_usuario=self.usuario2, fk_conversacion=conv, rol="miembro")
        return conv

    def test_listar_conversaciones_incluye_no_leidos_y_es_familia(self):
        conv = self._crear_conversacion_privada()
        Mensaje.objects.create(fk_emisor=self.usuario2, fk_conversacion=conv, contenido="Hola", leido=False)

        url = reverse("chat-conversaciones")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertIn("data", body)
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["no_leidos"], 1)
        self.assertFalse(body["data"][0]["es_familia"])

    def test_listar_conversaciones_marca_es_familia(self):
        conv = self._crear_conversacion_grupal()
        familia = Familia.objects.create(nombre_familia="Grupo test", estado=True)
        conv.fk_familia = familia
        conv.save(update_fields=["fk_familia"])

        url = reverse("chat-conversaciones")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertTrue(body["data"][0]["es_familia"])

    def test_crear_conversacion_privada_acepta_alias_fk_usuario(self):
        url = reverse("chat-conversaciones-crear-privada")
        response = self.client.post(url, {"fk_usuario": self.usuario2.id_usuario})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertIn("id_conversacion", body["data"])

    def test_crear_conversacion_privada_rechaza_id_no_numerico(self):
        url = reverse("chat-conversaciones-crear-privada")
        response = self.client.post(url, {"fk_usuario": "abc"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.json()["ok"])
        self.assertIn("número", response.json()["message"])

    def test_crear_conversacion_privada_usuario_inexistente(self):
        url = reverse("chat-conversaciones-crear-privada")
        response = self.client.post(url, {"fk_usuario": 99999})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.json()["ok"])

    def test_crear_conversacion_grupal_exitosa(self):
        url = reverse("chat-conversaciones-crear-grupal")
        payload = {
            "nombre": "Nuevo grupo",
            "fk_usuarios": [self.usuario2.id_usuario, self.usuario3.id_usuario],
        }
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertTrue(body["ok"])
        conv_id = body["data"]["id_conversacion"]
        self.assertEqual(Integrante.objects.filter(fk_conversacion_id=conv_id, estado=True).count(), 3)

    def test_agregar_integrante_reactiva_integrante_inactivo(self):
        conv = self._crear_conversacion_grupal()
        integrante = Integrante.objects.create(fk_usuario=self.usuario3, fk_conversacion=conv, estado=False)

        url = reverse("chat-conversaciones-agregar-integrante", args=[conv.id_conversacion])
        response = self.client.post(url, {"usuario_id": self.usuario3.id_usuario})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        integrante.refresh_from_db()
        self.assertTrue(integrante.estado)

    def test_get_or_reactivate_integrante_crea_nuevo(self):
        conv = self._crear_conversacion_grupal()
        integrante = views._get_or_reactivate_integrante(self.usuario3, conv)
        self.assertIsNotNone(integrante)
        self.assertTrue(integrante.estado)
        self.assertTrue(Integrante.objects.filter(pk=integrante.pk, estado=True).exists())

    def test_get_or_reactivate_integrante_reactiva_inactivo(self):
        conv = self._crear_conversacion_grupal()
        integrante = Integrante.objects.create(fk_usuario=self.usuario3, fk_conversacion=conv, estado=False)
        reactivado = views._get_or_reactivate_integrante(self.usuario3, conv)
        self.assertEqual(integrante.pk, reactivado.pk)
        self.assertTrue(reactivado.estado)

    def test_crear_conversacion_grupal_reporta_usuarios_faltantes(self):
        url = reverse("chat-conversaciones-crear-grupal")
        payload = {
            "nombre": "Grupo incompleto",
            "fk_usuarios": [self.usuario2.id_usuario, 99999],
        }
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertIn(99999, body["data"]["no_encontrados"])

    def test_crear_conversacion_grupal_rechaza_ids_no_numericos(self):
        url = reverse("chat-conversaciones-crear-grupal")
        payload = {"nombre": "Grupo", "fk_usuarios": ["abc"]}
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertIn("abc", body["data"]["invalidos"])

    def test_crear_conversacion_grupal_rechaza_fk_usuarios_string(self):
        url = reverse("chat-conversaciones-crear-grupal")
        payload = {"nombre": "Grupo", "fk_usuarios": "no es una lista"}
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("lista", response.json()["message"].lower())

    def test_agregar_integrante_acepta_alias_fk_usuario(self):
        conv = self._crear_conversacion_grupal()
        url = reverse("chat-conversaciones-agregar-integrante", args=[conv.id_conversacion])
        response = self.client.post(url, {"fk_usuario": self.usuario3.id_usuario})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Integrante.objects.filter(fk_usuario=self.usuario3, fk_conversacion=conv, estado=True).exists())

    def test_listar_mensajes_con_paginacion(self):
        conv = self._crear_conversacion_privada()
        for i in range(25):
            Mensaje.objects.create(fk_emisor=self.usuario2, fk_conversacion=conv, contenido=f"M{i}")

        url = reverse("chat-mensajes", args=[conv.id_conversacion])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertIn("data", body)
        self.assertIn("count", body["data"])
        self.assertIn("results", body["data"])
        self.assertEqual(body["data"]["count"], 25)

    def test_enviar_mensaje_con_documento_alias_conversacion_y_documento(self):
        conv = self._crear_conversacion_privada()
        url = reverse("chat-mensajes-enviar-con-documento")
        archivo = SimpleUploadedFile(
            "prueba.jpg",
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00",
            content_type="image/jpeg",
        )
        response = self.client.post(
            url,
            {
                "conversacion": conv.id_conversacion,
                "documento": archivo,
                "tipo_documento": "imagen",
                "contenido": "Mensaje con adjunto",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertIn("id_mensaje", body["data"])
        self.assertTrue(Documento.objects.filter(fk_usuario=self.usuario1).exists())

    def test_inactivar_mensaje_exitoso(self):
        conv = self._crear_conversacion_privada()
        mensaje = Mensaje.objects.create(fk_emisor=self.usuario1, fk_conversacion=conv, contenido="A borrar")

        url = reverse("chat-mensajes-inactivar", args=[mensaje.id_mensaje])
        response = self.client.patch(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.json())
        mensaje.refresh_from_db()
        self.assertFalse(mensaje.estado)

    def test_inactivar_mensaje_ventana_editable_expirada(self):
        conv = self._crear_conversacion_privada()
        mensaje = Mensaje.objects.create(fk_emisor=self.usuario1, fk_conversacion=conv, contenido="Antiguo")
        Mensaje.objects.filter(pk=mensaje.id_mensaje).update(creado_en=timezone.now() - timedelta(minutes=20))

        url = reverse("chat-mensajes-inactivar", args=[mensaje.id_mensaje])
        response = self.client.patch(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("15 minutos", str(response.json()))
        mensaje.refresh_from_db()
        self.assertTrue(mensaje.estado)

    def test_inactivar_mensaje_ajeno_denegado(self):
        conv = self._crear_conversacion_privada()
        mensaje = Mensaje.objects.create(fk_emisor=self.usuario2, fk_conversacion=conv, contenido="De user2")

        url = reverse("chat-mensajes-inactivar", args=[mensaje.id_mensaje])
        response = self.client.patch(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mensaje.refresh_from_db()
        self.assertTrue(mensaje.estado)

    def test_conversacion_leer_exitoso(self):
        conv = self._crear_conversacion_privada()
        msg_otro = Mensaje.objects.create(
            fk_emisor=self.usuario2,
            fk_conversacion=conv,
            contenido="De otro",
            leido=False,
        )
        msg_propio = Mensaje.objects.create(
            fk_emisor=self.usuario1,
            fk_conversacion=conv,
            contenido="Mio",
            leido=False,
        )

        url = reverse("chat-conversaciones-leer", args=[conv.id_conversacion])
        response = self.client.patch(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["marcados"], 1)

        msg_otro.refresh_from_db()
        self.assertTrue(msg_otro.leido)
        msg_propio.refresh_from_db()
        self.assertFalse(msg_propio.leido)

    def test_conversacion_leer_sin_mensajes_pendientes(self):
        conv = self._crear_conversacion_privada()
        Mensaje.objects.create(fk_emisor=self.usuario2, fk_conversacion=conv, contenido="x", leido=True)

        url = reverse("chat-conversaciones-leer", args=[conv.id_conversacion])
        response = self.client.patch(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["data"]["marcados"], 0)

    def test_crear_conversacion_privada_con_uno_mismo(self):
        url = reverse("chat-conversaciones-crear-privada")
        response = self.client.post(url, {"fk_usuario": self.usuario1.id_usuario})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.json()["ok"])
        self.assertIn("contigo mismo", response.json()["message"])

    def test_agregar_integrante_ya_activo(self):
        conv = self._crear_conversacion_grupal()
        url = reverse("chat-conversaciones-agregar-integrante", args=[conv.id_conversacion])
        # usuario2 ya es miembro desde _crear_conversacion_grupal
        response = self.client.post(url, {"usuario_id": self.usuario2.id_usuario})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(
            response.json()["message"],
            "El usuario ya es miembro de esta conversación.",
        )

    def test_renombrar_conversacion(self):
        conv = self._crear_conversacion_grupal()
        url = reverse("chat-conversaciones-renombrar", args=[conv.id_conversacion])
        response = self.client.patch(url, {"nombre": "Nuevo nombre grupo"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["nombre"], "Nuevo nombre grupo")
        conv.refresh_from_db()
        self.assertEqual(conv.nombre, "Nuevo nombre grupo")

    def test_listar_integrantes(self):
        conv = self._crear_conversacion_grupal()
        url = reverse("chat-conversaciones-integrantes", args=[conv.id_conversacion])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertIn("data", body)
        self.assertEqual(len(body["data"]), 2)
        nombres = {miembro["nombre_completo"] for miembro in body["data"]}
        self.assertIn("User1 Test", nombres)
        self.assertIn("User2 Test", nombres)

    # --- Edge cases: permisos y validación (coverage gaps de round 3) ---

    def test_renombrar_conversacion_privada_rechazado(self):
        conv = self._crear_conversacion_privada()
        url = reverse("chat-conversaciones-renombrar", args=[conv.id_conversacion])
        response = self.client.patch(url, {"nombre": "Otro"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_renombrar_conversacion_nombre_vacio(self):
        conv = self._crear_conversacion_grupal()
        url = reverse("chat-conversaciones-renombrar", args=[conv.id_conversacion])
        response = self.client.patch(url, {"nombre": "   "})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_renombrar_conversacion_usuario_no_miembro(self):
        conv = self._crear_conversacion_grupal()  # miembros: user1, user2
        self.client.force_authenticate(self.user3)  # user3 no es miembro
        url = reverse("chat-conversaciones-renombrar", args=[conv.id_conversacion])
        response = self.client.patch(url, {"nombre": "Hack"})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_listar_integrantes_usuario_no_miembro(self):
        conv = self._crear_conversacion_grupal()
        self.client.force_authenticate(self.user3)
        url = reverse("chat-conversaciones-integrantes", args=[conv.id_conversacion])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_agregar_integrante_usuario_no_miembro(self):
        conv = self._crear_conversacion_grupal()
        self.client.force_authenticate(self.user3)  # user3 no es miembro
        url = reverse("chat-conversaciones-agregar-integrante", args=[conv.id_conversacion])
        response = self.client.post(url, {"usuario_id": self.usuario2.id_usuario})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_conversacion_leer_usuario_no_miembro(self):
        conv = self._crear_conversacion_privada()
        Mensaje.objects.create(fk_emisor=self.usuario2, fk_conversacion=conv, contenido="x")
        self.client.force_authenticate(self.user3)
        url = reverse("chat-conversaciones-leer", args=[conv.id_conversacion])
        response = self.client.patch(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_conversacion_leer_conversacion_inexistente(self):
        url = reverse("chat-conversaciones-leer", args=[99999])
        response = self.client.patch(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_inactivar_mensaje_usuario_no_miembro(self):
        conv = self._crear_conversacion_privada()  # user1 emisor, user2 receptor
        mensaje = Mensaje.objects.create(fk_emisor=self.usuario1, fk_conversacion=conv, contenido="mío")
        # user1 sale de la conv (integrante inactivo) y trata de inactivar su mensaje.
        # Membership check runs before the emisor check, so a removed member gets 403
        # even if they authored the message.
        Integrante.objects.filter(fk_usuario=self.usuario1, fk_conversacion=conv).update(estado=False)
        url = reverse("chat-mensajes-inactivar", args=[mensaje.id_mensaje])
        response = self.client.patch(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_enviar_documento_usuario_no_miembro(self):
        conv = self._crear_conversacion_privada()  # user1 y user2
        self.client.force_authenticate(self.user3)  # user3 no es miembro
        url = reverse("chat-mensajes-enviar-con-documento")
        archivo = SimpleUploadedFile("a.txt", b"x", content_type="text/plain")
        response = self.client.post(
            url,
            {"conversacion": conv.id_conversacion, "documento": archivo, "tipo_documento": "imagen"},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_enviar_documento_archivo_grande(self):
        conv = self._crear_conversacion_privada()
        url = reverse("chat-mensajes-enviar-con-documento")
        grande = SimpleUploadedFile("big.bin", b"x" * (21 * 1024 * 1024), content_type="application/octet-stream")
        response = self.client.post(
            url,
            {
                "conversacion": conv.id_conversacion,
                "documento": grande,
                "tipo_documento": "imagen",
                "contenido": "",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_enviar_documento_tipo_invalido(self):
        conv = self._crear_conversacion_privada()
        url = reverse("chat-mensajes-enviar-con-documento")
        archivo = SimpleUploadedFile("a.txt", b"x", content_type="text/plain")
        response = self.client.post(
            url,
            {"conversacion": conv.id_conversacion, "documento": archivo, "tipo_documento": "documento"},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_enviar_documento_mime_invalido(self):
        try:
            import magic as _magiclib

            _magiclib.from_buffer(b"test", mime=True)
        except (ImportError, OSError):
            self.skipTest("python-magic no está disponible")
        conv = self._crear_conversacion_privada()
        url = reverse("chat-mensajes-enviar-con-documento")
        archivo = SimpleUploadedFile("foto.jpg", b"esto no es una imagen", content_type="image/jpeg")
        response = self.client.post(
            url,
            {"conversacion": conv.id_conversacion, "documento": archivo, "tipo_documento": "imagen"},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Conversacion detalle ───────────────────────────────────────

    def test_conversacion_detalle_exitoso(self):
        conv = self._crear_conversacion_grupal()
        url = reverse("chat-conversaciones-detalle", args=[conv.id_conversacion])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["tipo"], "grupal")
        self.assertEqual(body["data"]["nombre"], "Grupo test")

    def test_conversacion_detalle_usuario_no_miembro(self):
        conv = self._crear_conversacion_privada()
        self.client.force_authenticate(self.user3)
        url = reverse("chat-conversaciones-detalle", args=[conv.id_conversacion])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_conversacion_detalle_inexistente(self):
        url = reverse("chat-conversaciones-detalle", args=[99999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ── Usuario buscar ─────────────────────────────────────────────

    def test_usuarios_buscar_exitoso(self):
        url = reverse("chat-usuarios-buscar")
        response = self.client.get(url, {"q": "user2"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertGreaterEqual(len(body["data"]), 1)
        self.assertIn("id_usuario", body["data"][0])
        self.assertIn("nombre_completo", body["data"][0])

    def test_usuarios_buscar_sin_resultados(self):
        url = reverse("chat-usuarios-buscar")
        response = self.client.get(url, {"q": "zzzzz"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["data"]), 0)

    def test_usuarios_buscar_query_muy_corta(self):
        url = reverse("chat-usuarios-buscar")
        response = self.client.get(url, {"q": "ab"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["data"]), 0)

    def test_usuarios_buscar_sin_query(self):
        url = reverse("chat-usuarios-buscar")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["data"]), 0)

    # ── Post-review: CR3 — límite de 15 min ─────────────────────────

    def test_inactivar_mensaje_justo_antes_del_limite(self):
        conv = self._crear_conversacion_privada()
        mensaje = Mensaje.objects.create(fk_emisor=self.usuario1, fk_conversacion=conv, contenido="Borde")
        Mensaje.objects.filter(pk=mensaje.id_mensaje).update(
            creado_en=timezone.now() - timedelta(minutes=14, seconds=59),
        )

        url = reverse("chat-mensajes-inactivar", args=[mensaje.id_mensaje])
        response = self.client.patch(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_inactivar_mensaje_justo_despues_del_limite(self):
        conv = self._crear_conversacion_privada()
        mensaje = Mensaje.objects.create(fk_emisor=self.usuario1, fk_conversacion=conv, contenido="Borde")
        Mensaje.objects.filter(pk=mensaje.id_mensaje).update(
            creado_en=timezone.now() - timedelta(minutes=15, seconds=1),
        )

        url = reverse("chat-mensajes-inactivar", args=[mensaje.id_mensaje])
        response = self.client.patch(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Post-review: R3.1 — editar mensaje ──────────────────────────

    def test_editar_mensaje_exitoso(self):
        conv = self._crear_conversacion_privada()
        mensaje = Mensaje.objects.create(fk_emisor=self.usuario1, fk_conversacion=conv, contenido="Original")

        url = reverse("chat-mensajes-editar", args=[mensaje.id_mensaje])
        response = self.client.patch(url, {"contenido": "Editado"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertTrue(body["ok"])
        mensaje.refresh_from_db()
        self.assertEqual(mensaje.contenido, "Editado")
        self.assertTrue(mensaje.editado)

    def test_editar_mensaje_ajeno_denegado(self):
        conv = self._crear_conversacion_privada()
        mensaje = Mensaje.objects.create(fk_emisor=self.usuario2, fk_conversacion=conv, contenido="De otro")

        url = reverse("chat-mensajes-editar", args=[mensaje.id_mensaje])
        response = self.client.patch(url, {"contenido": "Hack"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_editar_mensaje_expirado(self):
        conv = self._crear_conversacion_privada()
        mensaje = Mensaje.objects.create(fk_emisor=self.usuario1, fk_conversacion=conv, contenido="Viejo")
        Mensaje.objects.filter(pk=mensaje.id_mensaje).update(
            creado_en=timezone.now() - timedelta(minutes=20),
        )

        url = reverse("chat-mensajes-editar", args=[mensaje.id_mensaje])
        response = self.client.patch(url, {"contenido": "Editado"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_editar_mensaje_inexistente(self):
        url = reverse("chat-mensajes-editar", args=[99999])
        response = self.client.patch(url, {"contenido": "Nope"})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ── Post-review: R3.2 — listar mensajes sin ser miembro ─────────

    def test_listar_mensajes_usuario_no_miembro(self):
        conv = self._crear_conversacion_privada()
        self.client.force_authenticate(self.user3)
        url = reverse("chat-mensajes", args=[conv.id_conversacion])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ── Post-review: R3.3 — crear conversación con usuario inactivo ─

    def test_crear_conversacion_privada_usuario_inactivo(self):
        self.usuario2.estado = False
        self.usuario2.save(update_fields=["estado"])
        url = reverse("chat-conversaciones-crear-privada")
        response = self.client.post(url, {"fk_usuario": self.usuario2.id_usuario})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ── Post-review: R3.4 — búsqueda excluye al usuario actual ──────

    def test_usuario_buscar_excluye_actual(self):
        url = reverse("chat-usuarios-buscar")
        response = self.client.get(url, {"q": "user1"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [u["id_usuario"] for u in response.json()["data"]]
        self.assertNotIn(self.usuario1.id_usuario, ids)

    # ── Post-review: R3.5 — grupo con creador en fk_usuarios ────────

    def test_crear_conversacion_grupal_creador_en_fk_usuarios(self):
        url = reverse("chat-conversaciones-crear-grupal")
        payload = {
            "nombre": "Grupo",
            "fk_usuarios": [
                self.usuario1.id_usuario,
                self.usuario2.id_usuario,
            ],
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        conv_id = response.json()["data"]["id_conversacion"]
        self.assertEqual(
            Integrante.objects.filter(fk_conversacion_id=conv_id, estado=True).count(),
            2,  # creator + user2, not duplicated
        )

    # ── Post-review: R4.3 — usuario inactivo no puede enviar ────────

    def test_enviar_mensaje_usuario_inactivo(self):
        self.usuario1.estado = False
        self.usuario1.save(update_fields=["estado"])
        conv = self._crear_conversacion_privada()
        url = reverse("chat-mensajes-enviar")
        response = self.client.post(
            url,
            {"fk_conversacion": conv.id_conversacion, "contenido": "Hola"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("desactivada", str(response.json()))

    def test_enviar_documento_usuario_inactivo(self):
        self.usuario1.estado = False
        self.usuario1.save(update_fields=["estado"])
        conv = self._crear_conversacion_privada()
        url = reverse("chat-mensajes-enviar-con-documento")
        archivo = SimpleUploadedFile("a.jpg", b"x", content_type="image/jpeg")
        response = self.client.post(
            url,
            {
                "conversacion": conv.id_conversacion,
                "documento": archivo,
                "tipo_documento": "imagen",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("desactivada", str(response.json()))

    # ── Post-review: CR1 — extensión de archivo inválida ────────────

    def test_enviar_documento_extension_invalida(self):
        conv = self._crear_conversacion_privada()
        url = reverse("chat-mensajes-enviar-con-documento")
        archivo = SimpleUploadedFile("virus.exe", b"x", content_type="application/octet-stream")
        response = self.client.post(
            url,
            {
                "conversacion": conv.id_conversacion,
                "documento": archivo,
                "tipo_documento": "imagen",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("extensión", response.json()["documento"][0].lower())

    # ── Post-review ronda 2: grupo sin integrantes ───────────────────

    def test_crear_conversacion_grupal_sin_integrantes(self):
        url = reverse("chat-conversaciones-crear-grupal")
        response = self.client.post(
            url,
            {"nombre": "Grupo", "fk_usuarios": []},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("integrante", response.json()["message"].lower())

    def test_crear_conversacion_grupal_solo_creador(self):
        url = reverse("chat-conversaciones-crear-grupal")
        response = self.client.post(
            url,
            {"nombre": "Grupo", "fk_usuarios": [self.usuario1.id_usuario]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("integrante", response.json()["message"].lower())

    # ── Post-review ronda 2: no_leidos excluye mensajes inválidos ────

    def test_no_leidos_excluye_mensajes_inactivos(self):
        conv = self._crear_conversacion_privada()
        Mensaje.objects.create(
            fk_emisor=self.usuario2,
            fk_conversacion=conv,
            contenido="visible",
            leido=False,
        )
        Mensaje.objects.create(
            fk_emisor=self.usuario2,
            fk_conversacion=conv,
            contenido="inactivo",
            leido=False,
            estado=False,
        )

        url = reverse("chat-conversaciones")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["data"][0]["no_leidos"], 1)

    def test_no_leidos_excluye_mensajes_sin_emisor(self):
        conv = self._crear_conversacion_privada()
        Mensaje.objects.create(
            fk_emisor=self.usuario2,
            fk_conversacion=conv,
            contenido="visible",
            leido=False,
        )
        Mensaje.objects.create(
            fk_emisor=None,
            fk_conversacion=conv,
            contenido="sin emisor",
            leido=False,
        )

        url = reverse("chat-conversaciones")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["data"][0]["no_leidos"], 1)

    # ── Post-review ronda 2: lista vacía ─────────────────────────────

    def test_listar_conversaciones_sin_conversaciones(self):
        self.client.force_authenticate(self.user3)
        url = reverse("chat-conversaciones")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["data"]), 0)

    # ── Post-review ronda 3: flujo completo ──────────────────────────

    def test_flujo_completo_enviar_leer_no_leidos(self):
        conv = self._crear_conversacion_privada()
        # user1 envía mensaje a user2
        url_enviar = reverse("chat-mensajes-enviar")
        self.client.post(
            url_enviar,
            {"fk_conversacion": conv.id_conversacion, "contenido": "Hola"},
        )

        # user2 ve no_leidos = 1
        self.client.force_authenticate(self.user2)
        url_lista = reverse("chat-conversaciones")
        response = self.client.get(url_lista)
        self.assertEqual(response.json()["data"][0]["no_leidos"], 1)

        # user2 marca como leído
        url_leer = reverse("chat-conversaciones-leer", args=[conv.id_conversacion])
        self.client.patch(url_leer)

        # no_leidos ahora 0
        response = self.client.get(url_lista)
        self.assertEqual(response.json()["data"][0]["no_leidos"], 0)

        self.client.force_authenticate(self.user1)

    def test_flujo_completo_con_documento(self):
        conv = self._crear_conversacion_privada()
        url = reverse("chat-mensajes-enviar-con-documento")
        archivo = SimpleUploadedFile(
            "foto.jpg",
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00",
            content_type="image/jpeg",
        )
        response = self.client.post(
            url,
            {
                "conversacion": conv.id_conversacion,
                "documento": archivo,
                "tipo_documento": "imagen",
                "contenido": "Con foto",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id_mensaje", response.json()["data"])

    def test_usuario_buscar_usuario_inactivo(self):
        self.usuario1.estado = False
        self.usuario1.save(update_fields=["estado"])
        url = reverse("chat-usuarios-buscar")
        response = self.client.get(url, {"q": "test"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_listar_mensajes_conversacion_inexistente(self):
        url = reverse("chat-mensajes", args=[99999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- Admin-only mutations and family-chat guards ---

    def test_solo_admin_puede_toggle_override(self):
        familia = Familia.objects.create(nombre_familia="Fam override", estado=True)
        familia.fk_jefe_familia = self.usuario1
        familia.save(update_fields=["fk_jefe_familia"])
        FamiliaUsuario.objects.create(fk_usuario=self.usuario1, fk_familia=familia, estado=True)
        FamiliaUsuario.objects.create(fk_usuario=self.usuario2, fk_familia=familia, estado=True)
        conv = chat_sync.ensure_family_chat(familia.id_familia)

        url = reverse("chat-conversaciones-override-nombre", args=[conv.id_conversacion])
        # user2 es miembro pero no admin
        self.client.force_authenticate(self.user2)
        response = self.client.patch(url, {"nombre_override": True}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.json()["ok"])

        # user1 es el jefe/admin
        self.client.force_authenticate(self.user1)
        response = self.client.patch(url, {"nombre_override": True}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_solo_admin_puede_renombrar_grupo(self):
        conv = self._crear_conversacion_grupal()
        url = reverse("chat-conversaciones-renombrar", args=[conv.id_conversacion])

        self.client.force_authenticate(self.user2)
        response = self.client.patch(url, {"nombre": "Hackeo"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.json()["ok"])

        self.client.force_authenticate(self.user1)
        response = self.client.patch(url, {"nombre": "Nuevo nombre"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_no_admin_no_puede_agregar_integrante(self):
        conv = self._crear_conversacion_grupal()
        self.client.force_authenticate(self.user2)
        url = reverse("chat-conversaciones-agregar-integrante", args=[conv.id_conversacion])
        response = self.client.post(url, {"usuario_id": self.usuario3.id_usuario})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.json()["ok"])

    def test_no_admin_no_puede_remover_integrante(self):
        conv = self._crear_conversacion_grupal()
        self.client.force_authenticate(self.user2)
        url = reverse("chat-conversaciones-remover-integrante", args=[conv.id_conversacion, self.usuario1.id_usuario])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.json()["ok"])

    def test_agregar_integrante_a_chat_familiar_rechazado(self):
        familia = Familia.objects.create(nombre_familia="Fam add", estado=True)
        familia.fk_jefe_familia = self.usuario1
        familia.save(update_fields=["fk_jefe_familia"])
        FamiliaUsuario.objects.create(fk_usuario=self.usuario1, fk_familia=familia, estado=True)
        FamiliaUsuario.objects.create(fk_usuario=self.usuario2, fk_familia=familia, estado=True)
        FamiliaUsuario.objects.create(fk_usuario=self.usuario3, fk_familia=familia, estado=True)
        conv = chat_sync.ensure_family_chat(familia.id_familia)

        url = reverse("chat-conversaciones-agregar-integrante", args=[conv.id_conversacion])
        response = self.client.post(url, {"usuario_id": self.usuario3.id_usuario})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("familia", response.json()["message"].lower())

    def test_remover_integrante_de_chat_familiar_rechazado(self):
        familia = Familia.objects.create(nombre_familia="Fam rm", estado=True)
        familia.fk_jefe_familia = self.usuario1
        familia.save(update_fields=["fk_jefe_familia"])
        FamiliaUsuario.objects.create(fk_usuario=self.usuario1, fk_familia=familia, estado=True)
        FamiliaUsuario.objects.create(fk_usuario=self.usuario2, fk_familia=familia, estado=True)
        conv = chat_sync.ensure_family_chat(familia.id_familia)

        url = reverse("chat-conversaciones-remover-integrante", args=[conv.id_conversacion, self.usuario2.id_usuario])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("familia", response.json()["message"].lower())
        # El integrante sigue activo porque la operación se rechaza.
        miembro = Integrante.objects.get(fk_usuario=self.usuario2, fk_conversacion=conv)
        self.assertTrue(miembro.estado)

    def test_es_familia_solo_familias_activas(self):
        conv = self._crear_conversacion_grupal()
        familia = Familia.objects.create(nombre_familia="Fam activa", estado=True)
        conv.fk_familia = familia
        conv.save(update_fields=["fk_familia"])

        url = reverse("chat-conversaciones")
        body = self.client.get(url).json()
        self.assertTrue(body["data"][0]["es_familia"])

        familia.estado = False
        familia.save(update_fields=["estado"])
        body = self.client.get(url).json()
        self.assertFalse(body["data"][0]["es_familia"])


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
class ChatFamiliaSyncTests(APITestCase):
    def setUp(self):
        self.user1, self.usuario1 = _crear_usuario("fsync1")
        self.user2, self.usuario2 = _crear_usuario("fsync2")
        self.user3, self.usuario3 = _crear_usuario("fsync3")
        self.client.force_authenticate(self.user1)

    def _crear_conversacion_grupal(self):
        conv = Conversacion.objects.create(tipo=True, nombre="Grupo fsync")
        Integrante.objects.create(fk_usuario=self.usuario1, fk_conversacion=conv, rol="admin")
        Integrante.objects.create(fk_usuario=self.usuario2, fk_conversacion=conv, rol="miembro")
        return conv

    def _crear_familia(self, jefe=None, miembros=None):
        familia = Familia.objects.create(nombre_familia="Fam test", estado=True)
        if jefe is not None:
            familia.fk_jefe_familia = jefe
            familia.save(update_fields=["fk_jefe_familia"])
        usuarios = miembros if miembros is not None else [self.usuario1, self.usuario2, self.usuario3]
        for u in usuarios:
            FamiliaUsuario.objects.get_or_create(fk_usuario=u, fk_familia=familia, defaults={"estado": True})
        return familia

    # 1. Remover integrante (endpoint) hace soft-delete idempotente.
    def test_remover_integrante_endpoints_soft_deletes(self):
        from rassa.blueprints.chat.services.chat_sync import ensure_family_chat  # noqa: F401 (import smoke)

        conv = self._crear_conversacion_grupal()
        url_add = reverse("chat-conversaciones-agregar-integrante", args=[conv.id_conversacion])
        self.client.post(url_add, {"usuario_id": self.usuario3.id_usuario})

        url_rm = reverse(
            "chat-conversaciones-remover-integrante", args=[conv.id_conversacion, self.usuario2.id_usuario]
        )
        response = self.client.delete(url_rm)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(Integrante.objects.get(fk_usuario=self.usuario2, fk_conversacion=conv).estado)
        self.assertEqual(Integrante.objects.filter(fk_conversacion=conv).count(), 3)

        # Idempotente: segunda eliminación -> 200.
        response2 = self.client.delete(url_rm)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

        # GET integrantes -> quedan 2 activos.
        url_int = reverse("chat-conversaciones-integrantes", args=[conv.id_conversacion])
        body = self.client.get(url_int).json()
        self.assertEqual(len(body["data"]), 2)

    # 2. Remover no-miembro -> 404.
    def test_remover_integrante_no_miembro_404(self):
        conv = self._crear_conversacion_grupal()
        url = reverse("chat-conversaciones-remover-integrante", args=[conv.id_conversacion, self.usuario3.id_usuario])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # 3. Renombrar chat familiar bloqueado sin override; permitido con override.
    def test_renombrar_chat_familiar_bloqueado_sin_override(self):
        conv = self._crear_conversacion_grupal()
        familia = self._crear_familia(jefe=self.usuario1)
        # Vincular la conversación existente a la familia y sincronizar roles.
        conv.fk_familia = familia
        conv.nombre_override = False
        conv.save(update_fields=["fk_familia", "nombre_override"])
        chat_sync.sync_family_roles(familia.id_familia)

        url = reverse("chat-conversaciones-renombrar", args=[conv.id_conversacion])
        response = self.client.patch(url, {"nombre": "Hack familiar"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("desacoplarlo mediante override", response.json()["message"])

        conv.nombre_override = True
        conv.save(update_fields=["nombre_override"])
        response2 = self.client.patch(url, {"nombre": "Nombre custom"})
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

    # 4. Crear grupal rechaza fk_familia manual.
    def test_crear_grupal_rechaza_fk_familia_manual(self):
        familia = self._crear_familia()
        url = reverse("chat-conversaciones-crear-grupal")
        response = self.client.post(
            url, {"nombre": "X", "fk_usuarios": [self.usuario2.id_usuario], "fk_familia": familia.id_familia}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["message"], "No se puede vincular una conversación a una familia manualmente.")

    # 5. Constraint unique_active_family_conversation.
    def test_unique_active_family_conversation(self):
        from django.db import transaction

        familia = self._crear_familia()
        Conversacion.objects.create(tipo=True, fk_familia=familia, estado=True)
        with self.assertRaises(Exception):
            with transaction.atomic():
                Conversacion.objects.create(tipo=True, fk_familia=familia, estado=True)
        # Una segunda inactiva con misma familia sí está permitida.
        Conversacion.objects.create(tipo=True, fk_familia=familia, estado=False)

    # 6. Integrante por defecto rol=miembro.
    def test_integrante_rol_default_miembro(self):
        conv = Conversacion.objects.create(tipo=True)
        integrante = Integrante.objects.create(fk_usuario=self.usuario1, fk_conversacion=conv)
        self.assertEqual(integrante.rol, "miembro")

    # 7. ensure_family_chat idempotente; jefe admin.
    def test_chat_sync_ensure_family_chat_idempotente(self):
        from rassa.blueprints.chat.services.chat_sync import ensure_family_chat

        familia = self._crear_familia(jefe=self.usuario1, miembros=[self.usuario1, self.usuario2])
        conv1 = ensure_family_chat(familia.id_familia)
        conv2 = ensure_family_chat(familia.id_familia)
        self.assertEqual(conv1.pk, conv2.pk)
        self.assertEqual(Integrante.objects.filter(fk_conversacion=conv1).count(), 2)
        jefe_int = Integrante.objects.get(fk_usuario=self.usuario1, fk_conversacion=conv1)
        self.assertEqual(jefe_int.rol, "admin")
        Integrante.objects.get(fk_usuario=self.usuario2, fk_conversacion=conv1)

    # 8. remove_family_member idempotente.
    def test_chat_sync_remove_member_idempotente(self):
        from rassa.blueprints.chat.services.chat_sync import add_family_member, ensure_family_chat, remove_family_member

        familia = self._crear_familia(miembros=[self.usuario1])
        ensure_family_chat(familia.id_familia)
        add_family_member(familia.id_familia, self.usuario2.id_usuario)
        remove_family_member(familia.id_familia, self.usuario2.id_usuario)
        remove_family_member(familia.id_familia, self.usuario2.id_usuario)  # no error
        integrante = Integrante.objects.get(fk_usuario=self.usuario2, fk_conversacion__fk_familia=familia)
        self.assertFalse(integrante.estado)

    # 9. deactivate + restore idempotente.
    def test_chat_sync_deactivate_and_restore(self):
        from rassa.blueprints.chat.services.chat_sync import (
            deactivate_family_chat,
            ensure_family_chat,
            restore_family_chat,
        )

        familia = self._crear_familia(jefe=self.usuario1, miembros=[self.usuario1, self.usuario2])
        conv = ensure_family_chat(familia.id_familia)

        self.assertTrue(deactivate_family_chat(familia.id_familia))
        conv.refresh_from_db()
        self.assertFalse(conv.estado)
        self.assertFalse(Integrante.objects.filter(fk_conversacion=conv, estado=True).exists())

        restore_family_chat(familia.id_familia)
        conv.refresh_from_db()
        self.assertTrue(conv.estado)
        self.assertEqual(Integrante.objects.filter(fk_conversacion=conv, estado=True).count(), 2)

        # Idempotente: restore de nuevo no duplica.
        restore_family_chat(familia.id_familia)
        self.assertEqual(Integrante.objects.filter(fk_conversacion=conv, estado=True).count(), 2)
