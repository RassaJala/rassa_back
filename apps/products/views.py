from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import connection
from .models import Product
from .serializers import ProductSerializer


class IsFarmerOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.role in ("farmer", "admin")


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer
    permission_classes = (permissions.IsAuthenticated, IsFarmerOrAdmin)

    def perform_create(self, serializer):
        serializer.save(farmer=self.request.user)


class ProductDetailView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request, product_id):
        sql = """
            SELECT
                p.id_producto AS id,
                p.nombre_producto AS name,
                p.descripcion AS description,
                p.es_perecedero AS is_perishable,
                ps.precio AS price,
                ps.stock AS stock,
                ps.foto AS image,
                ps.estado AS status,
                u.id_usuario AS farmer_id,
                CONCAT(per.nombre, ' ', per.apellido_paterno) AS farmer_name,
                c.nombre AS category_name
            FROM producto p
            INNER JOIN producto_semanal ps ON p.id_producto = ps.fk_producto
            INNER JOIN publicacion_semanal pub ON ps.fk_publicacion = pub.id_publicacion
            INNER JOIN usuario u ON pub.fk_agricultor = u.id_usuario
            INNER JOIN persona per ON u.fk_persona = per.id_persona
            LEFT JOIN categoria_producto c ON p.fk_categoria = c.id_categoria
            WHERE p.id_producto = %s AND ps.estado = 'activo'
            LIMIT 1
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [product_id])
            columns = [col[0] for col in cursor.description]
            row = cursor.fetchone()

        if not row:
            return Response(
                {"ok": False, "mensaje": "Producto no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        product = dict(zip(columns, row))
        return Response({"ok": True, "data": product}, status=status.HTTP_200_OK)


class ProductListView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        sql = """
            SELECT
                p.id_producto AS id,
                p.nombre_producto AS name,
                p.es_perecedero AS is_perishable,
                ps.precio AS price,
                ps.stock AS stock,
                ps.foto AS image,
                u.id_usuario AS farmer_id,
                CONCAT(per.nombre, ' ', per.apellido_paterno) AS farmer_name,
                c.nombre AS category_name
            FROM producto p
            INNER JOIN producto_semanal ps ON p.id_producto = ps.fk_producto
            INNER JOIN publicacion_semanal pub ON ps.fk_publicacion = pub.id_publicacion
            INNER JOIN usuario u ON pub.fk_agricultor = u.id_usuario
            INNER JOIN persona per ON u.fk_persona = per.id_persona
            LEFT JOIN categoria_producto c ON p.fk_categoria = c.id_categoria
            WHERE ps.estado = 'activo'
            ORDER BY p.id_producto
        """
        with connection.cursor() as cursor:
            cursor.execute(sql)
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()

        products = [dict(zip(columns, row)) for row in rows]
        return Response({"ok": True, "data": products}, status=status.HTTP_200_OK)
