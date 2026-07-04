"""Configuración WSGI para el proyecto Rassa.

Permite desplegar la aplicación con servidores WSGI (Gunicorn).
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rassa.settings")

application = get_wsgi_application()
