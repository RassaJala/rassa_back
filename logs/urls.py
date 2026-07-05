from django.urls import path

from .views import ActivityLogListView

app_name = "logs"

urlpatterns = [
    path("", ActivityLogListView.as_view(), name="list"),
]
