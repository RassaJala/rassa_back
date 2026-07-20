import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Count, OuterRef, Prefetch, Q, Subquery
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from rassa.models import Conversacion, Documento, Familia, Integrante, Mensaje, MensajeDocumento, Usuario
from rassa.views import _ok

from .serializers import (
    MensajeCreateSerializer,
    MensajeDocumentoCreateSerializer,
    MensajeSerializer,
    MensajeUpdateSerializer,
)


class MensajeListView(generics.ListAPIView):
    serializer_class = MensajeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        conversacion_id = self.kwargs.get("conversacion_id")

        try:
            conversacion = Conversacion.objects.get(pk=conversacion_id, estado=True)
        except Conversacion.DoesNotExist as err:
            raise NotFound("Conversación no encontrada.") from err

        if not conversacion.integrante_set.filter(fk_usuario=self.request.user.usuario, estado=True).exists():
            raise PermissionDenied("No eres miembro de esta conversación.")

        return (
            Mensaje.objects.filter(fk_conversacion_id=conversacion_id, estado=True)
            .select_related("fk_emisor__fk_persona")
            .order_by("-creado_en")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated = self.get_paginated_response(serializer.data).data
            return _ok(data=paginated)
        serializer = self.get_serializer(queryset, many=True)
        return _ok(data=serializer.data)


class MensajeCreateView(generics.CreateAPIView):
    serializer_class = MensajeCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["usuario"] = self.request.user.usuario
        return context

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mensaje = serializer.save()
        return _ok(
            data=MensajeSerializer(mensaje).data,
            message="Mensaje enviado correctamente.",
            status_code=status.HTTP_201_CREATED,
        )


class MensajeUpdateView(generics.UpdateAPIView):
    serializer_class = MensajeUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        if not hasattr(self, "_mensaje_cache"):
            mensaje_id = self.kwargs.get("mensaje_id")
            try:
                self._mensaje_cache = Mensaje.objects.get(pk=mensaje_id, estado=True)
            except Mensaje.DoesNotExist as err:
                raise NotFound("Mensaje no encontrado.") from err
        return self._mensaje_cache

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["mensaje"] = self.get_object()
        context["usuario"] = self.request.user.usuario
        return context

    def update(self, request, *args, **kwargs):
        mensaje = self.get_object()
        serializer = self.get_serializer(instance=mensaje, data=request.data)
        serializer.is_valid(raise_exception=True)
        mensaje = serializer.save()
        return _ok(
            data=MensajeSerializer(mensaje).data,
            message="Mensaje editado correctamente.",
        )


class MensajeLeerView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, mensaje_id):
        try:
            mensaje = Mensaje.objects.get(pk=mensaje_id, estado=True)
        except Mensaje.DoesNotExist as err:
            raise NotFound("Mensaje no encontrado.") from err

        if not mensaje.fk_conversacion.integrante_set.filter(fk_usuario=request.user.usuario, estado=True).exists():
            raise PermissionDenied("No eres miembro de esta conversación.")

        mensaje.leido = True
        mensaje.save(update_fields=["leido"])

        return Response({"ok": True, "mensaje": "Mensaje marcado como leído."})


class MensajeInactivarView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, mensaje_id):
        try:
            mensaje = Mensaje.objects.get(pk=mensaje_id, estado=True)
        except Mensaje.DoesNotExist:
            return Response(
                {"ok": False, "mensaje": "Mensaje no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if mensaje.fk_emisor_id != request.user.usuario.id_usuario:
            return Response(
                {
                    "ok": False,
                    "mensaje": "No puedes eliminar un mensaje que no te pertenece.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        antiguedad = timezone.now() - mensaje.creado_en
        if antiguedad > timedelta(minutes=15):
            return Response(
                {
                    "ok": False,
                    "mensaje": "Solo se pueden eliminar mensajes de los últimos 15 minutos.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        mensaje.estado = False
        mensaje.save(update_fields=["estado"])

        return Response({"ok": True, "mensaje": "Mensaje eliminado correctamente."})


class ConversacionPrivadaCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        usuario1 = request.user.usuario
        usuario2_id = request.data.get("usuario2") or request.data.get("fk_usuario")

        if not usuario2_id:
            return Response(
                {"ok": False, "mensaje": "El campo usuario2 es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            usuario2 = Usuario.objects.get(pk=usuario2_id, estado=True)
        except Usuario.DoesNotExist:
            return Response(
                {"ok": False, "mensaje": "El usuario no existe."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if usuario1.id_usuario == usuario2.id_usuario:
            return Response(
                {
                    "ok": False,
                    "mensaje": "No puedes crear una conversación contigo mismo.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            conv_ids = list(
                Integrante.objects.filter(
                    fk_usuario=usuario1,
                    estado=True,
                    fk_conversacion__tipo=False,
                    fk_conversacion__estado=True,
                )
                .select_for_update()
                .values_list("fk_conversacion_id", flat=True)
            )

            existing = (
                Integrante.objects.filter(
                    fk_usuario=usuario2,
                    estado=True,
                    fk_conversacion_id__in=conv_ids,
                    fk_conversacion__tipo=False,
                    fk_conversacion__estado=True,
                )
                .select_for_update()
                .select_related("fk_conversacion")
                .first()
            )

            if existing:
                return Response(
                    {
                        "ok": True,
                        "mensaje": "La conversación ya existe.",
                        "data": {"id_conversacion": existing.fk_conversacion_id},
                    }
                )

            conv = Conversacion.objects.create(tipo=False)
            Integrante.objects.create(fk_usuario=usuario1, fk_conversacion=conv)
            Integrante.objects.create(fk_usuario=usuario2, fk_conversacion=conv)

            return Response(
                {
                    "ok": True,
                    "mensaje": "Conversación creada correctamente.",
                    "data": {"id_conversacion": conv.id_conversacion},
                },
                status=status.HTTP_201_CREATED,
            )


class ConversacionGrupalCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        nombre = request.data.get("nombre")

        if not nombre or not nombre.strip():
            return Response(
                {"ok": False, "mensaje": "El campo nombre es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        usuario_creador = request.user.usuario
        fk_usuarios = request.data.get("fk_usuarios") or []

        with transaction.atomic():
            conv = Conversacion.objects.create(tipo=True, nombre=nombre.strip())
            Integrante.objects.create(fk_usuario=usuario_creador, fk_conversacion=conv)

            for uid in fk_usuarios:
                try:
                    usuario = Usuario.objects.get(pk=uid, estado=True)
                except Usuario.DoesNotExist:
                    continue
                Integrante.objects.get_or_create(
                    fk_usuario=usuario,
                    fk_conversacion=conv,
                    defaults={"estado": True},
                )

        return Response(
            {
                "ok": True,
                "mensaje": "Conversación grupal creada correctamente.",
                "data": {"id_conversacion": conv.id_conversacion},
            },
            status=status.HTTP_201_CREATED,
        )


class ConversacionRenombrarView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, conversacion_id):
        nombre = request.data.get("nombre")

        if not nombre or not nombre.strip():
            return Response(
                {"ok": False, "mensaje": "El campo nombre es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            conv = Conversacion.objects.get(pk=conversacion_id, estado=True)
        except Conversacion.DoesNotExist:
            return Response(
                {"ok": False, "mensaje": "Conversación no encontrada."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not conv.tipo:
            return Response(
                {
                    "ok": False,
                    "mensaje": "Solo puedes renombrar conversaciones grupales.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not conv.integrante_set.filter(fk_usuario=request.user.usuario, estado=True).exists():
            return Response(
                {
                    "ok": False,
                    "mensaje": "No eres miembro de esta conversación.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        conv.nombre = nombre.strip()
        conv.save(update_fields=["nombre"])

        return Response(
            {
                "ok": True,
                "mensaje": "Nombre de la conversación actualizado correctamente.",
                "data": {"id_conversacion": conv.id_conversacion, "nombre": conv.nombre},
            }
        )


class ConversacionAgregarIntegranteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, conversacion_id):
        usuario_id = request.data.get("usuario_id") or request.data.get("fk_usuario")

        if not usuario_id:
            return Response(
                {"ok": False, "mensaje": "El campo usuario_id es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            conv = Conversacion.objects.get(pk=conversacion_id, estado=True)
        except Conversacion.DoesNotExist:
            return Response(
                {"ok": False, "mensaje": "Conversación no encontrada."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not conv.tipo:
            return Response(
                {
                    "ok": False,
                    "mensaje": "Solo puedes agregar integrantes a conversaciones grupales.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        solicitante = request.user.usuario
        if not conv.integrante_set.filter(fk_usuario=solicitante, estado=True).exists():
            return Response(
                {
                    "ok": False,
                    "mensaje": "No eres miembro de esta conversación.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            usuario_nuevo = Usuario.objects.get(pk=usuario_id, estado=True)
        except Usuario.DoesNotExist:
            return Response(
                {"ok": False, "mensaje": "El usuario no existe."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if conv.integrante_set.filter(fk_usuario=usuario_nuevo, estado=True).exists():
            return Response(
                {
                    "ok": False,
                    "mensaje": "El usuario ya es miembro de esta conversación.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        Integrante.objects.create(fk_usuario=usuario_nuevo, fk_conversacion=conv)

        return Response(
            {
                "ok": True,
                "mensaje": "Integrante agregado correctamente.",
                "data": {"id_conversacion": conv.id_conversacion},
            },
            status=status.HTTP_201_CREATED,
        )


class ConversacionIntegrantesListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, conversacion_id):
        try:
            conv = Conversacion.objects.get(pk=conversacion_id, estado=True)
        except Conversacion.DoesNotExist:
            return Response(
                {"ok": False, "mensaje": "Conversación no encontrada."},
                status=status.HTTP_404_NOT_FOUND,
            )

        usuario = request.user.usuario
        if not conv.integrante_set.filter(fk_usuario=usuario, estado=True).exists():
            return Response(
                {
                    "ok": False,
                    "mensaje": "No eres miembro de esta conversación.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        integrantes = conv.integrante_set.filter(estado=True).select_related("fk_usuario__fk_persona")

        result = []
        for integrante in integrantes:
            user = integrante.fk_usuario
            persona = user.fk_persona
            apellido_m = persona.apellido_materno or ""
            nombre_completo = f"{persona.nombre} {persona.apellido_paterno} {apellido_m}".strip()
            result.append(
                {
                    "id_miembro": integrante.id_miembro,
                    "id_usuario": user.id_usuario,
                    "nombre_completo": nombre_completo,
                    "correo": user.correo,
                    "creado_en": integrante.creado_en.isoformat(),
                }
            )

        return Response({"ok": True, "data": result})


class ConversacionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        usuario = request.user.usuario

        ultimo_subq = Mensaje.objects.filter(fk_conversacion=OuterRef("pk"), estado=True).order_by("-creado_en")

        conversaciones = (
            Conversacion.objects.filter(
                integrante__fk_usuario=usuario,
                integrante__estado=True,
                estado=True,
            )
            .annotate(
                ultimo_mensaje_contenido=Subquery(ultimo_subq.values("contenido")[:1]),
                ultimo_mensaje_creado_en=Subquery(ultimo_subq.values("creado_en")[:1]),
                no_leidos_count=Count(
                    "mensaje",
                    filter=Q(
                        mensaje__leido=False,
                        mensaje__estado=True,
                        mensaje__fk_emisor__isnull=False,
                    )
                    & ~Q(mensaje__fk_emisor=usuario),
                ),
            )
            .prefetch_related(
                Prefetch(
                    "integrante_set",
                    queryset=Integrante.objects.filter(estado=True).select_related("fk_usuario__fk_persona"),
                    to_attr="integrantes_activos",
                )
            )
            .distinct()
        )

        result = []
        for conv in conversaciones:
            if conv.tipo:
                nombre = conv.nombre
            else:
                otros = [i for i in conv.integrantes_activos if i.fk_usuario_id != usuario.id_usuario]
                if otros:
                    persona = otros[0].fk_usuario.fk_persona
                    apellido_m = persona.apellido_materno or ""
                    nombre = f"{persona.nombre} {persona.apellido_paterno} {apellido_m}".strip()
                else:
                    nombre = "Sin nombre"

            es_familia = False
            if conv.tipo and conv.nombre:
                es_familia = Familia.objects.filter(
                    nombre_familia=conv.nombre,
                    estado=True,
                ).exists()

            result.append(
                {
                    "id_conversacion": conv.id_conversacion,
                    "tipo": conv.tipo,
                    "nombre": nombre,
                    "ultimo_mensaje": conv.ultimo_mensaje_contenido,
                    "ultimo_mensaje_creado_en": (
                        conv.ultimo_mensaje_creado_en.isoformat() if conv.ultimo_mensaje_creado_en else None
                    ),
                    "no_leidos": conv.no_leidos_count,
                    "es_familia": es_familia,
                }
            )

        return _ok(data=result)


class MensajeDocumentoCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_context(self):
        return {"usuario": self.request.user.usuario}

    def post(self, request):
        mutable_data = request.data.copy()
        if "conversacion" in mutable_data and "fk_conversacion" not in mutable_data:
            mutable_data["fk_conversacion"] = mutable_data.pop("conversacion")
        if "documento" in mutable_data and "archivo" not in mutable_data:
            mutable_data["archivo"] = mutable_data.pop("documento")

        serializer = MensajeDocumentoCreateSerializer(
            data=mutable_data,
            context={"usuario": request.user.usuario},
        )
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        usuario = request.user.usuario
        archivo = data["archivo"]

        docs_dir = Path(settings.MEDIA_ROOT) / "documentos"
        docs_dir.mkdir(parents=True, exist_ok=True)

        nombre_archivo = f"{uuid.uuid4().hex}_{archivo.name}"
        ruta = docs_dir / nombre_archivo
        with open(ruta, "wb") as f:
            for chunk in archivo.chunks():
                f.write(chunk)

        with transaction.atomic():
            documento = Documento.objects.create(
                fk_usuario=usuario,
                nombre_documento=archivo.name,
                url_documento=f"documentos/{nombre_archivo}",
                tipo_documento=data["tipo_documento"],
            )

            mensaje = Mensaje.objects.create(
                fk_emisor=usuario,
                fk_conversacion_id=data["fk_conversacion"],
                contenido=data.get("contenido") or "",
            )

            MensajeDocumento.objects.create(
                fk_mensaje=mensaje,
                fk_documento=documento,
            )

        return Response(
            {
                "ok": True,
                "mensaje": "Mensaje con documento enviado correctamente.",
                "data": {
                    "id_mensaje": mensaje.id_mensaje,
                    "id_documento": documento.id_documento,
                    "url_documento": f"documentos/{nombre_archivo}",
                },
            },
            status=status.HTTP_201_CREATED,
        )
