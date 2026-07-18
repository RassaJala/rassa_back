from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied

from rassa.models import Conversacion, Mensaje
from rassa.views import _ok

from .serializers import MensajeCreateSerializer, MensajeSerializer


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
