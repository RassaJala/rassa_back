from rest_framework import viewsets, permissions
from .models import Order
from .serializers import OrderSerializer


class IsBuyerOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role in ("buyer", "admin")


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = (permissions.IsAuthenticated, IsBuyerOrAdmin)

    def get_queryset(self):
        user = self.request.user
        if user.role == "admin":
            return Order.objects.all()
        return Order.objects.filter(buyer=user)

    def perform_create(self, serializer):
        serializer.save(buyer=self.request.user)
