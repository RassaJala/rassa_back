import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction

from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from rassa.models import Conversacion, Documento, Mensaje, MensajeDocumento
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
            conversacion = Conversacion.objects.get(
                pk=conversacion_id, estado=True
            )
        except Conversacion.DoesNotExist as err:
            raise NotFound("Conversación no encontrada.") from err

        if not conversacion.integrante_set.filter(
            fk_usuario=self.request.user.usuario, estado=True
        ).exists():
            raise PermissionDenied("No eres miembro de esta conversación.")

        return (
            Mensaje.objects.filter(
                fk_conversacion_id=conversacion_id, estado=True
            )
            .select_related("fk_emisor__fk_persona")
            .order_by("-creado_en")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
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
        mensaje_id = self.kwargs.get("mensaje_id")
        try:
            return Mensaje.objects.get(pk=mensaje_id, estado=True)
        except Mensaje.DoesNotExist as err:
            raise NotFound("Mensaje no encontrado.") from err

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

        if not mensaje.fk_conversacion.integrante_set.filter(
            fk_usuario=request.user.usuario, estado=True
        ).exists():
            raise PermissionDenied("No eres miembro de esta conversación.")

        mensaje.leido = True
        mensaje.save(update_fields=["leido"])

        return Response({"ok": True, "mensaje": "Mensaje marcado como leído."})


class MensajeDocumentoCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_context(self):
        return {"usuario": self.request.user.usuario}

    def post(self, request):
        serializer = MensajeDocumentoCreateSerializer(
            data=request.data,
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
