from django.db.models import Q
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAdminUser

from .models import ActivityLog
from .serializers import ActivityLogSerializer


class ActivityLogListView(ListAPIView):
    serializer_class = ActivityLogSerializer
    permission_classes = [IsAdminUser]
    queryset = ActivityLog.objects.select_related("user").all()

    def get_queryset(self):
        queryset = super().get_queryset()

        user_param = self.request.query_params.get("user")
        if user_param:
            try:
                queryset = queryset.filter(user_id=int(user_param))
            except (TypeError, ValueError):
                queryset = queryset.filter(user__username__icontains=user_param)

        action_param = self.request.query_params.get("action")
        if action_param:
            queryset = queryset.filter(action__icontains=action_param)

        date_param = self.request.query_params.get("date")
        if date_param:
            queryset = queryset.filter(timestamp__date=date_param)

        return queryset
