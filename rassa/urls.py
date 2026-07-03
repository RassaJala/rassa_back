"""Configuración de rutas URL del proyecto Rassa.

Endpoints disponibles:
    - /admin/              → Panel de administración Django
    - /api/auth/           → Autenticación (login, register, me, refresh)

Todos los endpoints de autenticación están bajo /api/auth/.
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("rassa.auth.urls")),
]
