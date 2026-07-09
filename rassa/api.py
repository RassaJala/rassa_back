from rest_framework import serializers, status, viewsets
from rest_framework.response import Response

from rassa.models import CategoriaProducto, Unidad


class SoftDeleteModelViewSet(viewsets.ModelViewSet):
    """ViewSet base que convierte DELETE en desactivación."""

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.estado = False
        instance.save(update_fields=["estado"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_queryset(self):
        queryset = super().get_queryset()
        estado = self.request.query_params.get("estado", "true").strip().lower()
        if estado in ("all", "todos", "todas"):
            return queryset
        if estado in ("1", "true", "yes", "on"):
            return queryset.filter(estado=True)
        if estado in ("0", "false", "no", "off"):
            return queryset.filter(estado=False)
        return queryset.filter(estado=True)


class CategoriaProductoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoriaProducto
        fields = [
            "id_categoria",
            "nombre",
            "descripcion",
            "creado_en",
            "estado",
        ]
        read_only_fields = ["id_categoria", "creado_en"]


class UnidadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unidad
        fields = [
            "id_unidad",
            "tipo",
            "abreviatura",
            "creado_en",
            "estado",
        ]
        read_only_fields = ["id_unidad", "creado_en"]


class CategoriaProductoViewSet(SoftDeleteModelViewSet):
    queryset = CategoriaProducto.objects.all().order_by("id_categoria")
    serializer_class = CategoriaProductoSerializer


class UnidadViewSet(SoftDeleteModelViewSet):
    queryset = Unidad.objects.all().order_by("id_unidad")
    serializer_class = UnidadSerializer
