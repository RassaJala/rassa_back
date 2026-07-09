from django.urls import path

from .views import ActivityLogViewSet

urlpatterns = [
    path("", ActivityLogViewSet.as_view({"get": "list"}), name="activitylog-list"),
    path("<int:pk>/", ActivityLogViewSet.as_view({"get": "retrieve"}), name="activitylog-detail"),
]
