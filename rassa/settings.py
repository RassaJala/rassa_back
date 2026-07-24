"""
Configuración de Django para el proyecto Rassa.

Esta es la configuración principal del backend. Lee variables de entorno
desde un archivo .env usando python-decouple.

Variables requeridas:
    - SECRET_KEY: Clave secreta de Django (obligatorio en producción).
    - DEBUG: Modo debug (True/False).
    - DATABASE_URL: URL de conexión a la base de datos PostgreSQL.
    - ALLOWED_HOSTS: Hosts permitidos (separados por coma).
    - CORS_ALLOWED_ORIGINS: Orígenes CORS permitidos (separados por coma).
"""

import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# === SECURITY ===
SECRET_KEY = config("SECRET_KEY", default="changeme-in-production")
if SECRET_KEY == "changeme-in-production" and not config("DEBUG", default=False, cast=bool):
    raise ImproperlyConfigured("SECRET_KEY must be overridden in production.")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="*", cast=Csv())

# === APPS ===
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
]

INSTALLED_APPS = (
    DJANGO_APPS
    + THIRD_PARTY_APPS
    + [
        "rassa.apps.RassaConfig",
        "logs.apps.LogsConfig",
    ]
)

# === MIDDLEWARE ===
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "logs.middleware.ActivityLogMiddleware",
]

ROOT_URLCONF = "rassa.urls"

# === TEMPLATES ===
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "rassa.wsgi.application"

# === DATABASE ===
DATABASE_URL = config("DATABASE_URL", default="sqlite:///db.sqlite3")
DATABASES = {"default": dj_database_url.config(default=DATABASE_URL, conn_max_age=600)}

# === AUTH ===
# Using default Django User model for authentication.
# Auth endpoints in rassa/auth/ module provide login, register, me.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# === REST FRAMEWORK ===
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
}

# === LOGGING ===
EXCLUDED_PATHS = [
    "/admin/",
    "/api/token/",
    "/api/token/refresh/",
]
ADMIN_ROLE_NAME = "Admin"

# === SIMPLE JWT ===
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=2),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
}

# === THROTTLING ===
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = [
    "rest_framework.throttling.AnonRateThrottle",
    "rest_framework.throttling.UserRateThrottle",
    "rest_framework.throttling.ScopedRateThrottle",
]
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {
    "anon": "60/minute",
    "user": "1000/hour",
    "register": "30/minute",
    "login": "30/minute",
    "change_password": "10/hour",
    "catalog_read": "60/minute",
    "catalog_write": "60/hour",
    "publicaciones": "30/hour",
    "publicaciones_write": "10/hour",
    "admin_write": "30/hour",
    "chat_read": "60/minute",
    "chat_write": "30/minute",
    "admin_users": "30/minute",
    "pedidos_cambiar_estado": "30/hour",
    "publicaciones_current": "60/minute",
}

# === TEST: disable throttling so test suites don't exhaust rate limits ===
if "test" in sys.argv or "pytest" in sys.modules:
    REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []

# === CORS ===
CORS_ALLOW_ALL_ORIGINS = config("CORS_ALLOW_ALL_ORIGINS", default=True, cast=bool)
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:8081,http://localhost:19006",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True

# === I18N ===
LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Argentina/Buenos_Aires"
USE_I18N = True
USE_TZ = True

# === STATIC / MEDIA ===
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# === DEFAULT ===
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# === GOOGLE DRIVE ===
GOOGLE_DRIVE_CREDENTIALS_PATH = config("GOOGLE_DRIVE_CREDENTIALS_PATH", default=None)
GOOGLE_DRIVE_FOLDER_ID = config("GOOGLE_DRIVE_FOLDER_ID", default=None)
GOOGLE_DRIVE_CLIENT_ID = config("GOOGLE_DRIVE_CLIENT_ID", default=None)
GOOGLE_DRIVE_CLIENT_SECRET = config("GOOGLE_DRIVE_CLIENT_SECRET", default=None)
GOOGLE_DRIVE_REFRESH_TOKEN = config("GOOGLE_DRIVE_REFRESH_TOKEN", default=None)

# === TRUSTED PROXIES ===
TRUSTED_PROXIES = config("TRUSTED_PROXIES", default="", cast=Csv())
