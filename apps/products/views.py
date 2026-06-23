from rest_framework import viewsets, permissions
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
