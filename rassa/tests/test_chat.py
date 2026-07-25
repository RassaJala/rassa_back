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

from rassa.models import Conversacion, Documento, Familia, Integrante, Mensaje, Persona, Rol, Usuario

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
        "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
        "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
        "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
        "PAGE_SIZE": 20,
        "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
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
        Integrante.objects.create(fk_usuario=self.usuario1, fk_conversacion=conv)
        Integrante.objects.create(fk_usuario=self.usuario2, fk_conversacion=conv)
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
        self._crear_conversacion_grupal()
        Familia.objects.create(nombre_familia="Grupo test", estado=True)

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
        self.assertIn("lista", response.json()["mensaje"].lower())

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
        archivo = SimpleUploadedFile("prueba.txt", b"contenido de prueba", content_type="text/plain")
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

    def test_leer_mensaje_exitoso(self):
        conv = self._crear_conversacion_privada()
        mensaje = Mensaje.objects.create(fk_emisor=self.usuario2, fk_conversacion=conv, contenido="Hola", leido=False)

        url = reverse("chat-mensajes-leer", args=[mensaje.id_mensaje])
        response = self.client.patch(url, data={})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("message", response.json())
        mensaje.refresh_from_db()
        self.assertTrue(mensaje.leido)

    def test_crear_conversacion_privada_con_uno_mismo(self):
        url = reverse("chat-conversaciones-crear-privada")
        response = self.client.post(url, {"fk_usuario": self.usuario1.id_usuario})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.json()["ok"])
        self.assertIn("contigo mismo", response.json()["mensaje"])

    def test_agregar_integrante_ya_activo(self):
        conv = self._crear_conversacion_grupal()
        url = reverse("chat-conversaciones-agregar-integrante", args=[conv.id_conversacion])
        # usuario2 ya es miembro desde _crear_conversacion_grupal
        response = self.client.post(url, {"usuario_id": self.usuario2.id_usuario})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(
            response.json()["mensaje"],
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
