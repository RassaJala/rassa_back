from rest_framework import serializers

from .models import ActivityLog


class ActivityLogSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ActivityLog
        fields = ["id", "user", "action", "ip_address", "user_agent", "method", "path", "timestamp"]
