from django.contrib import admin

from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "method", "path", "ip_address")
    search_fields = ("action", "path", "ip_address", "user_agent")
    list_filter = ("timestamp", "method")
