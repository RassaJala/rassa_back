from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from rassa.auth_views import CustomTokenObtainPairView

urlpatterns = [
    path("admin/", admin.site.urls),
    # JWT — Spanish error messages via CustomTokenObtainPairSerializer
    path("api/token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
]
