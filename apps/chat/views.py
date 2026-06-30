import os

from django.conf import settings
from django.db import connection
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from .serializers import MensajeConversacionSerializer, EnviarMensajeSerializer, EditarMensajeSerializer


def dictfetchall(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


class MensajesConversacionView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, conversacion_id):
        sql = """
            SELECT
                m.id_mensaje,
                u.id_usuario,
                CONCAT(p.nombre, ' ', p.apellido_paterno) AS emisor,
                m.contenido,
                m.leido,
                m.creado_en,

                d.id_documento,
                d.nombre_documento,
                d.url_documento,
                d.tipo_documento

            FROM mensaje m

            INNER JOIN usuario u
                ON m.fk_emisor = u.id_usuario

            INNER JOIN persona p
                ON u.fk_persona = p.id_persona

            LEFT JOIN mensajes_documentos md
                ON md.fk_mensaje = m.id_mensaje

            LEFT JOIN documento d
                ON d.id_documento = md.fk_documento

            WHERE m.fk_conversacion = %s AND m.estado = TRUE

            ORDER BY m.creado_en
        """

        with connection.cursor() as cursor:
            cursor.execute(sql, [conversacion_id])
            rows = dictfetchall(cursor)

        serializer = MensajeConversacionSerializer(data=rows, many=True)
        serializer.is_valid(raise_exception=True)

        return Response(serializer.data, status=status.HTTP_200_OK)


class EnviarMensajeView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        serializer = EnviarMensajeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        fk_emisor = serializer.validated_data["fk_emisor"]
        fk_conversacion = serializer.validated_data["fk_conversacion"]
        contenido = serializer.validated_data["contenido"]

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM usuario WHERE id_usuario = %s",
                [fk_emisor],
            )
            if not cursor.fetchone():
                return Response(
                    {"ok": False, "mensaje": "El usuario emisor no existe."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cursor.execute(
                "SELECT 1 FROM conversacion WHERE id_conversacion = %s",
                [fk_conversacion],
            )
            if not cursor.fetchone():
                return Response(
                    {"ok": False, "mensaje": "La conversación no existe."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cursor.execute(
                """INSERT INTO mensaje (fk_emisor, fk_conversacion, contenido, leido, estado)
                   VALUES (%s, %s, %s, FALSE, TRUE)""",
                [fk_emisor, fk_conversacion, contenido],
            )

        return Response(
            {"ok": True, "mensaje": "Mensaje enviado correctamente."},
            status=status.HTTP_201_CREATED,
        )


class EditarMensajeView(APIView):
    permission_classes = (permissions.AllowAny,)

    def put(self, request, mensaje_id):
        serializer = EditarMensajeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        contenido = serializer.validated_data["contenido"]

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM mensaje WHERE id_mensaje = %s",
                [mensaje_id],
            )
            if not cursor.fetchone():
                return Response(
                    {"ok": False, "mensaje": "El mensaje no existe."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            cursor.execute(
                "UPDATE mensaje SET contenido = %s WHERE id_mensaje = %s",
                [contenido, mensaje_id],
            )

        return Response(
            {"ok": True, "mensaje": "Mensaje actualizado correctamente."},
            status=status.HTTP_200_OK,
        )


class LeerMensajeView(APIView):
    permission_classes = (permissions.AllowAny,)

    def patch(self, request, mensaje_id):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM mensaje WHERE id_mensaje = %s",
                [mensaje_id],
            )
            if not cursor.fetchone():
                return Response(
                    {"ok": False, "mensaje": "El mensaje no existe."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            cursor.execute(
                "UPDATE mensaje SET leido = TRUE WHERE id_mensaje = %s",
                [mensaje_id],
            )

        return Response(
            {"ok": True, "mensaje": "Mensaje marcado como leído."},
            status=status.HTTP_200_OK,
        )


MAX_FILE_SIZE = 20 * 1024 * 1024
TIPOS_VALIDOS = {"imagen", "audio", "video"}


class EnviarMensajeConDocumentoView(APIView):
    permission_classes = (permissions.AllowAny,)
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        fk_usuario = request.data.get("fk_usuario")
        fk_conversacion = request.data.get("fk_conversacion")
        tipo_documento = request.data.get("tipo_documento")
        contenido = request.data.get("contenido")
        archivo = request.FILES.get("archivo")

        if not all([fk_usuario, fk_conversacion, tipo_documento, archivo]):
            return Response(
                {"ok": False, "mensaje": "Faltan campos requeridos: fk_usuario, fk_conversacion, tipo_documento, archivo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if tipo_documento not in TIPOS_VALIDOS:
            return Response(
                {"ok": False, "mensaje": f"tipo_documento debe ser uno de: {', '.join(TIPOS_VALIDOS)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if archivo.size > MAX_FILE_SIZE:
            return Response(
                {"ok": False, "mensaje": "El archivo supera el tamaño máximo de 20MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_dir = os.path.join(settings.BASE_DIR, "file")
        os.makedirs(file_dir, exist_ok=True)

        file_name = archivo.name
        file_path = os.path.join(file_dir, file_name)
        with open(file_path, "wb") as f:
            for chunk in archivo.chunks():
                f.write(chunk)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM usuario WHERE id_usuario = %s",
                [fk_usuario],
            )
            if not cursor.fetchone():
                return Response(
                    {"ok": False, "mensaje": "El usuario no existe."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cursor.execute(
                "SELECT 1 FROM conversacion WHERE id_conversacion = %s",
                [fk_conversacion],
            )
            if not cursor.fetchone():
                return Response(
                    {"ok": False, "mensaje": "La conversación no existe."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cursor.execute(
                """INSERT INTO mensaje (fk_emisor, fk_conversacion, contenido, leido, estado)
                   VALUES (%s, %s, NULLIF(%s, ''), FALSE, TRUE)
                   RETURNING id_mensaje""",
                [fk_usuario, fk_conversacion, contenido],
            )
            mensaje_id = cursor.fetchone()[0]

            cursor.execute(
                """INSERT INTO documento (fk_usuario, nombre_documento, url_documento, tipo_documento, estado)
                   VALUES (%s, %s, %s, %s, TRUE)
                   RETURNING id_documento""",
                [fk_usuario, file_name, f"file/{file_name}", tipo_documento],
            )
            documento_id = cursor.fetchone()[0]

            cursor.execute(
                "INSERT INTO mensajes_documentos (fk_mensaje, fk_documento, estado) VALUES (%s, %s, TRUE)",
                [mensaje_id, documento_id],
            )

        return Response(
            {
                "ok": True,
                "mensaje": "Mensaje con documento enviado correctamente.",
                "data": {
                    "id_mensaje": mensaje_id,
                    "id_documento": documento_id,
                    "url_documento": f"file/{file_name}",
                },
            },
            status=status.HTTP_201_CREATED,
        )


class ConversacionesUsuarioView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, usuario_id):
        sql = """
            SELECT
                c.id_conversacion,
                c.tipo,
                CASE
                    WHEN c.tipo = FALSE THEN (
                        SELECT CONCAT(p.nombre, ' ', p.apellido_paterno)
                        FROM integrantes i2
                        INNER JOIN usuario u2 ON i2.fk_usuario = u2.id_usuario
                        INNER JOIN persona p ON u2.fk_persona = p.id_persona
                        WHERE i2.fk_conversacion = c.id_conversacion
                          AND i2.fk_usuario != %s
                          AND i2.estado = TRUE
                        LIMIT 1
                    )
                    ELSE c.nombre
                END AS nombre,
                (
                    SELECT contenido FROM mensaje
                    WHERE fk_conversacion = c.id_conversacion AND estado = TRUE
                    ORDER BY creado_en DESC LIMIT 1
                ) AS ultimo_mensaje,
                (
                    SELECT creado_en FROM mensaje
                    WHERE fk_conversacion = c.id_conversacion AND estado = TRUE
                    ORDER BY creado_en DESC LIMIT 1
                ) AS ultimo_mensaje_creado_en
            FROM conversacion c
            INNER JOIN integrantes i ON c.id_conversacion = i.fk_conversacion
            WHERE i.fk_usuario = %s AND c.estado = TRUE AND i.estado = TRUE
            ORDER BY ultimo_mensaje_creado_en DESC NULLS LAST
        """

        with connection.cursor() as cursor:
            cursor.execute(sql, [usuario_id, usuario_id])
            rows = dictfetchall(cursor)

        return Response(rows, status=status.HTTP_200_OK)


class CrearConversacionPrivadaView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        usuario1 = request.data.get("usuario1")
        usuario2 = request.data.get("usuario2")

        if not usuario1 or not usuario2:
            return Response(
                {"ok": False, "mensaje": "Faltan campos requeridos: usuario1, usuario2."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if int(usuario1) == int(usuario2):
            return Response(
                {"ok": False, "mensaje": "Los usuarios deben ser diferentes."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id_usuario FROM usuario WHERE id_usuario IN (%s, %s)",
                [usuario1, usuario2],
            )
            existing_users = cursor.fetchall()
            if len(existing_users) != 2:
                return Response(
                    {"ok": False, "mensaje": "Uno o ambos usuarios no existen."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cursor.execute(
                """SELECT c.id_conversacion
                   FROM conversacion c
                   WHERE c.tipo = FALSE AND c.estado = TRUE
                     AND (SELECT COUNT(*) FROM integrantes
                          WHERE fk_conversacion = c.id_conversacion AND estado = TRUE) = 2
                     AND EXISTS (SELECT 1 FROM integrantes
                                 WHERE fk_conversacion = c.id_conversacion
                                   AND fk_usuario = %s AND estado = TRUE)
                     AND EXISTS (SELECT 1 FROM integrantes
                                 WHERE fk_conversacion = c.id_conversacion
                                   AND fk_usuario = %s AND estado = TRUE)""",
                [usuario1, usuario2],
            )
            existing = cursor.fetchone()
            if existing:
                return Response(
                    {
                        "ok": True,
                        "mensaje": "La conversación ya existe.",
                        "data": {"id_conversacion": existing[0]},
                    },
                    status=status.HTTP_200_OK,
                )

            cursor.execute(
                "INSERT INTO conversacion (tipo, estado) VALUES (FALSE, TRUE) RETURNING id_conversacion",
            )
            conv_id = cursor.fetchone()[0]

            cursor.execute(
                "INSERT INTO integrantes (fk_usuario, fk_conversacion, estado) VALUES (%s, %s, TRUE)",
                [usuario1, conv_id],
            )
            cursor.execute(
                "INSERT INTO integrantes (fk_usuario, fk_conversacion, estado) VALUES (%s, %s, TRUE)",
                [usuario2, conv_id],
            )

        return Response(
            {
                "ok": True,
                "mensaje": "Conversación creada correctamente.",
                "data": {"id_conversacion": conv_id},
            },
            status=status.HTTP_201_CREATED,
        )


class CrearConversacionGrupalView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        nombre = request.data.get("nombre")
        usuario_creador = request.data.get("usuario_creador")

        if not nombre or not usuario_creador:
            return Response(
                {"ok": False, "mensaje": "Faltan campos requeridos: nombre, usuario_creador."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM usuario WHERE id_usuario = %s",
                [usuario_creador],
            )
            if not cursor.fetchone():
                return Response(
                    {"ok": False, "mensaje": "El usuario no existe."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cursor.execute(
                "INSERT INTO conversacion (nombre, tipo, estado) VALUES (%s, TRUE, TRUE) RETURNING id_conversacion",
                [nombre],
            )
            conv_id = cursor.fetchone()[0]

            cursor.execute(
                "INSERT INTO integrantes (fk_usuario, fk_conversacion, estado) VALUES (%s, %s, TRUE)",
                [usuario_creador, conv_id],
            )

        return Response(
            {
                "ok": True,
                "mensaje": "Conversación grupal creada correctamente.",
                "data": {"id_conversacion": conv_id},
            },
            status=status.HTTP_201_CREATED,
        )


class AgregarIntegranteView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request, conversacion_id):
        usuario_id = request.data.get("usuario_id")

        if not usuario_id:
            return Response(
                {"ok": False, "mensaje": "Falta el campo requerido: usuario_id."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tipo, estado FROM conversacion WHERE id_conversacion = %s",
                [conversacion_id],
            )
            conv = cursor.fetchone()
            if not conv:
                return Response(
                    {"ok": False, "mensaje": "La conversación no existe."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if not conv[1]:
                return Response(
                    {"ok": False, "mensaje": "La conversación está desactivada."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not conv[0]:
                return Response(
                    {"ok": False, "mensaje": "Solo se pueden agregar integrantes a conversaciones grupales."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cursor.execute(
                "SELECT 1 FROM usuario WHERE id_usuario = %s",
                [usuario_id],
            )
            if not cursor.fetchone():
                return Response(
                    {"ok": False, "mensaje": "El usuario no existe."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cursor.execute(
                "SELECT 1 FROM integrantes WHERE fk_conversacion = %s AND fk_usuario = %s",
                [conversacion_id, usuario_id],
            )
            if cursor.fetchone():
                return Response(
                    {"ok": False, "mensaje": "El usuario ya es miembro de esta conversación."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cursor.execute(
                "INSERT INTO integrantes (fk_usuario, fk_conversacion, estado) VALUES (%s, %s, TRUE)",
                [usuario_id, conversacion_id],
            )

        return Response(
            {"ok": True, "mensaje": "Integrante agregado correctamente."},
            status=status.HTTP_201_CREATED,
        )


class InactivarMensajeView(APIView):
    permission_classes = (permissions.AllowAny,)

    def patch(self, request, mensaje_id):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT creado_en FROM mensaje WHERE id_mensaje = %s AND estado = TRUE",
                [mensaje_id],
            )
            row = cursor.fetchone()
            if not row:
                return Response(
                    {"ok": False, "mensaje": "El mensaje no existe o ya fue eliminado."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            from django.utils import timezone
            from datetime import timedelta

            ahora = timezone.now()
            creado_en = row[0]
            if timezone.is_naive(creado_en):
                creado_en = timezone.make_aware(creado_en)
            diferencia = ahora - creado_en

            if diferencia > timedelta(minutes=15):
                return Response(
                    {"ok": False, "mensaje": "Solo se pueden eliminar mensajes de los últimos 15 minutos."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            cursor.execute(
                "UPDATE mensaje SET estado = FALSE WHERE id_mensaje = %s",
                [mensaje_id],
            )

        return Response(
            {"ok": True, "mensaje": "Mensaje eliminado correctamente."},
            status=status.HTTP_200_OK,
        )
