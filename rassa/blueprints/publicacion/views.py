from datetime import date, timedelta

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from rassa.models import ProductoSemanal, PublicacionSemanal
from rassa.permissions.role_permissions import AGRICULTOR, HasRole
from rassa.views import CatalogPagination, _ok

from .serializers import ProductoSemanalSerializer, PublicacionSerializer


def calcular_proximo_lunes():
    hoy = date.today()
    dias_hasta_lunes = (7 - hoy.weekday()) % 7
    if dias_hasta_lunes == 0:
        dias_hasta_lunes = 7
    prox_lunes = hoy + timedelta(days=dias_hasta_lunes)
    return prox_lunes, prox_lunes.isocalendar()[1]


class PublicacionViewSet(viewsets.ViewSet):
    pagination_class = CatalogPagination

    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasRole(AGRICULTOR)]

    def get_queryset(self):
        return PublicacionSemanal.objects.filter(
            fk_agricultor=self.request.user.usuario
        ).order_by('-creado_en')

    @property
    def paginator(self):
        if not hasattr(self, '_paginator'):
            self._paginator = self.pagination_class()
        return self._paginator

    def list(self, request):
        queryset = self.get_queryset()
        estado = request.query_params.get('estado')
        if estado:
            queryset = queryset.filter(estado=estado)

        page = self.paginator.paginate_queryset(queryset, request)
        if page is not None:
            serializer = PublicacionSerializer(page, many=True)
            return _ok(data=self.paginator.get_paginated_response(serializer.data).data)

        serializer = PublicacionSerializer(queryset, many=True)
        return _ok(data=serializer.data)

    def create(self, request):
        prox_lunes, semana = calcular_proximo_lunes()
        publicacion = PublicacionSemanal.objects.create(
            fk_agricultor=request.user.usuario,
            fecha_publicacion=prox_lunes,
            semana=semana,
            estado='borrador',
        )
        serializer = PublicacionSerializer(publicacion)
        return _ok(
            data=serializer.data,
            message='Publicación creada correctamente.',
            status_code=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, pk=None):
        try:
            publicacion = self.get_queryset().get(pk=pk)
        except PublicacionSemanal.DoesNotExist as err:
            raise NotFound('Publicación no encontrada.') from err
        serializer = PublicacionSerializer(publicacion)
        return _ok(data=serializer.data)

    def partial_update(self, request, pk=None):
        try:
            publicacion = self.get_queryset().get(pk=pk)
        except PublicacionSemanal.DoesNotExist as err:
            raise NotFound('Publicación no encontrada.') from err

        if publicacion.estado != 'borrador':
            return Response(
                {'error': 'Solo se puede modificar una publicación en estado borrador.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PublicacionSerializer(
            publicacion, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return _ok(data=serializer.data, message='Publicación actualizada correctamente.')

    def destroy(self, request, pk=None):
        try:
            publicacion = self.get_queryset().get(pk=pk)
        except PublicacionSemanal.DoesNotExist as err:
            raise NotFound('Publicación no encontrada.') from err

        if publicacion.estado != 'borrador':
            return Response(
                {'error': 'Solo se puede eliminar una publicación en estado borrador.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        publicacion.delete()
        return _ok(message='Publicación eliminada correctamente.')

    @action(detail=True, methods=['post'], url_path='publish')
    def publish(self, request, pk=None):
        try:
            publicacion = self.get_queryset().get(pk=pk)
        except PublicacionSemanal.DoesNotExist as err:
            raise NotFound('Publicación no encontrada.') from err

        if publicacion.estado != 'borrador':
            return Response(
                {'error': 'Solo se puede publicar una publicación en estado borrador.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        items = publicacion.productosemanal_set.filter(estado='activo')
        if not items.exists():
            return Response(
                {'error': 'No hay productos activos para publicar.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        errores = []
        for item in items:
            errores_item = {}
            if item.stock <= 0:
                errores_item['stock'] = 'El stock debe ser mayor a 0.'
            if item.precio <= 0:
                errores_item['precio'] = 'El precio debe ser mayor a 0.'
            if not item.fk_unidad_id:
                errores_item['fk_unidad'] = 'La unidad es requerida.'
            if not item.foto or item.foto.strip() == '':
                errores_item['foto'] = 'La foto es requerida para publicar.'
            if errores_item:
                errores.append({
                    'id_producto_semanal': item.id_producto_semanal,
                    **errores_item,
                })

        if errores:
            return Response({'productos': errores}, status=status.HTTP_400_BAD_REQUEST)

        publicacion.estado = 'publicado'
        publicacion.save(update_fields=['estado'])
        serializer = PublicacionSerializer(publicacion)
        return _ok(data=serializer.data, message='Publicación publicada correctamente.')

    @action(detail=True, methods=['post'], url_path='close')
    def close(self, request, pk=None):
        try:
            publicacion = self.get_queryset().get(pk=pk)
        except PublicacionSemanal.DoesNotExist as err:
            raise NotFound('Publicación no encontrada.') from err

        if publicacion.estado != 'publicado':
            return Response(
                {'error': 'Solo se puede cerrar una publicación en estado publicado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        publicacion.estado = 'cerrado'
        publicacion.save(update_fields=['estado'])
        serializer = PublicacionSerializer(publicacion)
        return _ok(data=serializer.data, message='Publicación cerrada correctamente.')


class ProductoSemanalViewSet(viewsets.ViewSet):
    def get_permissions(self):
        return [permissions.IsAuthenticated(), HasRole(AGRICULTOR)]

    def _get_publicacion(self, pub_id, request):
        try:
            return PublicacionSemanal.objects.get(
                pk=pub_id, fk_agricultor=request.user.usuario
            )
        except PublicacionSemanal.DoesNotExist as err:
            raise NotFound('Publicación no encontrada.') from err

    def list(self, request, pub_id=None):
        publicacion = self._get_publicacion(pub_id, request)
        items = publicacion.productosemanal_set.filter(estado='activo')
        serializer = ProductoSemanalSerializer(items, many=True)
        return _ok(data=serializer.data)

    def create(self, request, pub_id=None):
        publicacion = self._get_publicacion(pub_id, request)
        if publicacion.estado != 'borrador':
            return Response(
                {'error': 'Solo se pueden agregar productos a una publicación en estado borrador.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ProductoSemanalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(fk_publicacion=publicacion)
        return _ok(
            data=serializer.data,
            message='Producto agregado correctamente.',
            status_code=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, pub_id=None, pk=None):
        publicacion = self._get_publicacion(pub_id, request)
        if publicacion.estado != 'borrador':
            return Response(
                {'error': 'Solo se pueden modificar productos en una publicación en estado borrador.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            item = publicacion.productosemanal_set.get(pk=pk)
        except ProductoSemanal.DoesNotExist as err:
            raise NotFound('Producto no encontrado.') from err

        serializer = ProductoSemanalSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return _ok(data=serializer.data, message='Producto actualizado correctamente.')

    def destroy(self, request, pub_id=None, pk=None):
        publicacion = self._get_publicacion(pub_id, request)
        if publicacion.estado != 'borrador':
            return Response(
                {'error': 'Solo se pueden eliminar productos en una publicación en estado borrador.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            item = publicacion.productosemanal_set.get(pk=pk)
        except ProductoSemanal.DoesNotExist as err:
            raise NotFound('Producto no encontrado.') from err

        item.estado = 'inactivo'
        item.save(update_fields=['estado'])
        return _ok(message='Producto eliminado correctamente.')
