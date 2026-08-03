"""Pruebas unitarias para utilidades compartidas (rassa/utils.py)."""

from django.test import TestCase

from rassa.models import Persona, Rol, Usuario
from rassa.utils import nombre_completo


class UtilsTest(TestCase):
    """Pruebas unitarias para la función nombre_completo."""

    def test_nombre_completo_con_usuario_valido(self):
        persona = Persona.objects.create(
            nombre="Juan",
            apellido_paterno="Pérez",
            fecha_nacimiento="1990-01-01",
            sexo="M",
            domicilio="Calle Falsa 123",
        )
        rol = Rol.objects.create(nombre_rol="Cliente", descripcion="Cliente")
        usuario = Usuario.objects.create(fk_persona=persona, fk_rol=rol)
        self.assertEqual(nombre_completo(usuario), "Juan Pérez")

    def test_nombre_completo_con_usuario_none(self):
        self.assertIsNone(nombre_completo(None))

    def test_nombre_completo_con_usuario_sin_persona(self):
        usuario = Usuario()
        self.assertIsNone(nombre_completo(usuario))
