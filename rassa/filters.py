"""Filters for product endpoints using django-filter."""

import django_filters

from rassa.models import Producto


class ProductoFilter(django_filters.FilterSet):
    """Filtros para el listado de productos.

    Query params soportados:
        ?categoria=<id>       Filtrar por categoría (fk_categoria)
        ?nombre=<texto>       Búsqueda parcial por nombre (icontains)
        ?es_perecedero=true   Filtrar por si es perecedero
        ?precio_min=<n>       Precio mínimo
        ?precio_max=<n>       Precio máximo
        ?unidad=<id>          Filtrar por unidad de medida
    """

    categoria = django_filters.NumberFilter(field_name="fk_categoria_id")
    nombre = django_filters.CharFilter(field_name="nombre_producto", lookup_expr="icontains")
    es_perecedero = django_filters.BooleanFilter(field_name="es_perecedero")
    precio_min = django_filters.NumberFilter(field_name="precio", lookup_expr="gte")
    precio_max = django_filters.NumberFilter(field_name="precio", lookup_expr="lte")
    unidad = django_filters.NumberFilter(field_name="fk_unidad_id")

    class Meta:
        model = Producto
        fields = ["categoria", "nombre", "es_perecedero", "precio_min", "precio_max", "unidad"]
