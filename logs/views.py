from rest_framework import viewsets
from rest_framework.permissions import BasePermission, IsAuthenticated

from django.conf import settings

from rassa.models import Log, Usuario

from .serializers import LogSerializer

ADMIN_ROLE_NAME = getattr(settings, "ADMIN_ROLE_NAME", "Admin")


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return Usuario.objects.filter(fk_user=request.user, fk_rol__nombre_rol=ADMIN_ROLE_NAME).exists()


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Log.objects.select_related("fk_usuario").all()
    serializer_class = LogSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        if descripcion := params.get("descripcion"):
            qs = qs.filter(descripcion__icontains=descripcion)
        if ip := params.get("ip"):
            qs = qs.filter(ip__icontains=ip)
        if usuario_id := params.get("usuario_id"):
            qs = qs.filter(fk_usuario_id=usuario_id)
        if start := params.get("start"):
            qs = qs.filter(creado_en__gte=start)
        if end := params.get("end"):
            qs = qs.filter(creado_en__lte=end)

        return qs
