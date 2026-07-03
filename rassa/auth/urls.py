"""Rutas de autenticación para el frontend.

Endpoints diseñados para ser consumidos por el AuthContext.tsx
del frontend React Native.

Rutas:
    - POST /api/auth/login-api/  → Login con email/contraseña
    - POST /api/auth/register/   → Registro de nuevo usuario
    - GET  /api/auth/me/         → Datos del usuario autenticado
    - POST /api/auth/refresh/    → Renovar access token

Referencia:
    Documento Técnico v3, Fase 13.4 - Módulo M3 (Usuarios y Roles).
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import LoginView, RegisterView, MeView

app_name = "auth"

urlpatterns = [
    path("login-api/", LoginView.as_view(), name="login"),
    path("register/", RegisterView.as_view(), name="register"),
    path("me/", MeView.as_view(), name="me"),
    path("refresh/", TokenRefreshView.as_view(), name="refresh"),
]
