"""Temporary debug script for unidad create/sequence issues."""
import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rassa.settings")
django.setup()

from django.db import connection  # noqa: E402

from rassa.models import Unidad  # noqa: E402

print("Before create:", list(Unidad.objects.values("id_unidad", "nombre", "abreviatura", "tipo")))
try:
    unit = Unidad.objects.create(nombre="Gramo", abreviatura="g", tipo="Gramo", estado=True)
    print("Created:", unit.id_unidad, unit.nombre)
except Exception as exc:
    print("Error:", type(exc).__name__, exc)

with connection.cursor() as cursor:
    cursor.execute("SELECT last_value, is_called FROM unidad_id_unidad_seq")
    print("Sequence:", cursor.fetchone())
