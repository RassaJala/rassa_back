"""Pruebas unitarias para el módulo de Familias."""

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from rassa.models import Familia, FamiliaUsuario, Persona, Rol, Usuario


class FamiliasTestCase(TestCase):
    """Caso de prueba para la gestión de Familias."""

    def setUp(self):
        self.client = APIClient()

        # Crear roles necesarios
        self.rol_admin = Rol.objects.create(id_rol=1, nombre_rol="Admin", descripcion="Administrador")
        self.rol_cliente = Rol.objects.create(id_rol=2, nombre_rol="Cliente", descripcion="Cliente")

        # Crear personas y usuarios de prueba
        self.user_admin = User.objects.create_superuser(
            username="admin", email="admin@rassa.com", password="password123"
        )
        self.persona_admin = Persona.objects.create(
            nombre="Admin",
            apellido_paterno="Rassa",
            fecha_nacimiento="1990-01-01",
            sexo="M",
            domicilio="Calle Admin 123",
        )
        self.usuario_admin = Usuario.objects.create(
            fk_user=self.user_admin,
            fk_persona=self.persona_admin,
            telefono="1234567890",
            correo="admin@rassa.com",
            fk_rol=self.rol_admin,
        )

        self.user_cliente1 = User.objects.create_user(
            username="cliente1", email="cliente1@rassa.com", password="password123"
        )
        self.persona_cliente1 = Persona.objects.create(
            nombre="Cliente",
            apellido_paterno="Uno",
            fecha_nacimiento="1995-05-05",
            sexo="F",
            domicilio="Calle Cliente 456",
        )
        self.usuario_cliente1 = Usuario.objects.create(
            fk_user=self.user_cliente1,
            fk_persona=self.persona_cliente1,
            telefono="0987654321",
            correo="cliente1@rassa.com",
            fk_rol=self.rol_cliente,
        )

        self.user_cliente2 = User.objects.create_user(
            username="cliente2", email="cliente2@rassa.com", password="password123"
        )
        self.persona_cliente2 = Persona.objects.create(
            nombre="Cliente",
            apellido_paterno="Dos",
            fecha_nacimiento="1996-06-06",
            sexo="M",
            domicilio="Calle Cliente 789",
        )
        self.usuario_cliente2 = Usuario.objects.create(
            fk_user=self.user_cliente2,
            fk_persona=self.persona_cliente2,
            telefono="1122334455",
            correo="cliente2@rassa.com",
            fk_rol=self.rol_cliente,
        )

        # Autenticar como Admin por defecto
        self.client.force_authenticate(user=self.user_admin)

    def test_crear_familia_exito(self):
        """Valida la creación exitosa de una familia por el administrador."""
        response = self.client.post(
            "/api/familias/grupos/",
            {"nombre_familia": "Familia Test", "detalle_familia": "Detalles de prueba"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["nombre_familia"], "Familia Test")
        self.assertEqual(Familia.objects.filter(nombre_familia="Familia Test").count(), 1)

    def test_crear_familia_nombre_invalido(self):
        """Valida que falle si el nombre es demasiado corto."""
        response = self.client.post(
            "/api/familias/grupos/",
            {"nombre_familia": "Fa", "detalle_familia": "Detalles"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre_familia", response.data)

    def test_exclusividad_miembro_familia(self):
        """Valida que un usuario no pueda pertenecer a más de una familia activa."""
        familia1 = Familia.objects.create(nombre_familia="Familia Uno")
        familia2 = Familia.objects.create(nombre_familia="Familia Dos")

        # Agregar a familia 1 (Exito)
        response1 = self.client.post(
            "/api/familias/miembros/",
            {"fk_usuario": self.usuario_cliente1.id_usuario, "fk_familia": familia1.id_familia},
            format="json",
        )
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

        # Intentar agregar a familia 2 (Fallo de validación)
        response2 = self.client.post(
            "/api/familias/miembros/",
            {"fk_usuario": self.usuario_cliente1.id_usuario, "fk_familia": familia2.id_familia},
            format="json",
        )
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_usuario", response2.data)

    def test_asignar_jefe_familia(self):
        """Valida la asignación y cambio de jefe de familia."""
        familia = Familia.objects.create(nombre_familia="Familia Test")
        # Primero debe ser miembro
        FamiliaUsuario.objects.create(fk_usuario=self.usuario_cliente1, fk_familia=familia)

        # Asignar jefe
        response = self.client.post(
            f"/api/familias/grupos/{familia.id_familia}/asignar-jefe/",
            {"fk_jefe_familia": self.usuario_cliente1.id_usuario},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        familia.refresh_from_db()
        self.assertEqual(familia.fk_jefe_familia, self.usuario_cliente1)

    def test_asignar_jefe_no_miembro(self):
        """Valida que un no miembro no pueda ser asignado como jefe."""
        familia = Familia.objects.create(nombre_familia="Familia Test")
        response = self.client.post(
            f"/api/familias/grupos/{familia.id_familia}/asignar-jefe/",
            {"fk_jefe_familia": self.usuario_cliente1.id_usuario},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_soft_delete_familia_miembros(self):
        """Valida que al eliminar una familia se desactiven lógicamente sus miembros."""
        familia = Familia.objects.create(nombre_familia="Familia Test")
        miembro = FamiliaUsuario.objects.create(fk_usuario=self.usuario_cliente1, fk_familia=familia)

        response = self.client.delete(f"/api/familias/grupos/{familia.id_familia}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        familia.refresh_from_db()
        miembro.refresh_from_db()
        self.assertFalse(familia.estado)
        self.assertFalse(miembro.estado)

    def test_fk_jefe_familia_read_only(self):
        """Valida que el campo fk_jefe_familia sea de solo lectura en FamiliaSerializer."""
        # 1. Intentar crear una familia enviando fk_jefe_familia directo
        response = self.client.post(
            "/api/familias/grupos/",
            {
                "nombre_familia": "Familia Bypass",
                "fk_jefe_familia": self.usuario_cliente1.id_usuario,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["fk_jefe_familia"])

        # 2. Intentar actualizar una familia enviando fk_jefe_familia directo
        familia = Familia.objects.create(nombre_familia="Familia Edit")
        response2 = self.client.patch(
            f"/api/familias/grupos/{familia.id_familia}/",
            {"fk_jefe_familia": self.usuario_cliente1.id_usuario},
            format="json",
        )
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertIsNone(response2.data["fk_jefe_familia"])

    def test_agregar_miembro_inactivo_o_familia_inactiva(self):
        """Valida que no se puedan agregar miembros inactivos o a familias inactivas."""
        familia_activa = Familia.objects.create(nombre_familia="Familia Activa")
        familia_inactiva = Familia.objects.create(nombre_familia="Familia Inactiva", estado=False)

        # Crear usuario inactivo
        user_inactivo = User.objects.create_user(
            username="inactivo", email="inactivo@rassa.com", password="password123"
        )
        persona_inactiva = Persona.objects.create(
            nombre="Inactivo",
            apellido_paterno="Usuario",
            fecha_nacimiento="1995-05-05",
            sexo="M",
            domicilio="Calle Inactiva 123",
        )
        usuario_inactivo = Usuario.objects.create(
            fk_user=user_inactivo,
            fk_persona=persona_inactiva,
            telefono="1234567890",
            correo="inactivo@rassa.com",
            fk_rol=self.rol_cliente,
            estado=False,
        )

        # 1. Intentar agregar usuario inactivo a familia activa -> Fallo
        response = self.client.post(
            "/api/familias/miembros/",
            {"fk_usuario": usuario_inactivo.id_usuario, "fk_familia": familia_activa.id_familia},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_usuario", response.data)

        # 2. Intentar agregar usuario activo a familia inactiva -> Fallo
        response2 = self.client.post(
            "/api/familias/miembros/",
            {"fk_usuario": self.usuario_cliente1.id_usuario, "fk_familia": familia_inactiva.id_familia},
            format="json",
        )
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_familia", response2.data)

    def test_re_asociar_usuario_despues_de_soft_delete(self):
        """Valida que un usuario se pueda asociar a otra familia si la anterior se desactivó."""
        familia1 = Familia.objects.create(nombre_familia="Familia Vieja")
        miembro_rel = FamiliaUsuario.objects.create(fk_usuario=self.usuario_cliente1, fk_familia=familia1)

        # Desactivar lógicamente la familia (esto desactiva también al miembro)
        response = self.client.delete(f"/api/familias/grupos/{familia1.id_familia}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verificar que la relación anterior está desactivada
        miembro_rel.refresh_from_db()
        self.assertFalse(miembro_rel.estado)

        # Crear nueva familia
        familia2 = Familia.objects.create(nombre_familia="Familia Nueva")

        # Asociar a la nueva familia (esto fallaba con IntegrityError por el OneToOneField)
        response2 = self.client.post(
            "/api/familias/miembros/",
            {"fk_usuario": self.usuario_cliente1.id_usuario, "fk_familia": familia2.id_familia},
            format="json",
        )
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)

    def test_asignar_jefe_no_numerico(self):
        """Valida que enviar un jefe no numérico retorne 400 en lugar de crashear (500)."""
        familia = Familia.objects.create(nombre_familia="Familia Test")
        response = self.client.post(
            f"/api/familias/grupos/{familia.id_familia}/asignar-jefe/",
            {"fk_jefe_familia": "no-numerico"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_jefe_familia", response.data)

    def test_bypass_validacion_patch_estado(self):
        """Valida que un PATCH de reactivación de estado no evada la validación de exclusividad."""
        familia1 = Familia.objects.create(nombre_familia="Familia Uno")
        familia2 = Familia.objects.create(nombre_familia="Familia Dos")

        # El usuario pertenece de forma activa a familia1
        FamiliaUsuario.objects.create(fk_usuario=self.usuario_cliente1, fk_familia=familia1, estado=True)

        # El usuario tiene una relación inactiva en familia2
        rel_inactiva = FamiliaUsuario.objects.create(
            fk_usuario=self.usuario_cliente1, fk_familia=familia2, estado=False
        )

        # Probamos la validación del serializador directamente al recibir un PATCH parcial
        from rassa.blueprints.familias.serializers import FamiliaMiembroSerializer

        serializer = FamiliaMiembroSerializer(instance=rel_inactiva, data={"estado": True}, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn("fk_usuario", serializer.errors)

    def test_miembro_viewset_http_method_restrictions(self):
        """Valida que PUT y PATCH estén deshabilitados en el ViewSet de miembros."""
        familia = Familia.objects.create(nombre_familia="Familia Test")
        rel = FamiliaUsuario.objects.create(fk_usuario=self.usuario_cliente1, fk_familia=familia, estado=True)

        # Intentar PUT -> 405 Method Not Allowed
        response_put = self.client.put(
            f"/api/familias/miembros/{rel.id_familia_usuario}/",
            {"fk_usuario": self.usuario_cliente1.id_usuario, "fk_familia": familia.id_familia, "estado": False},
            format="json",
        )
        self.assertEqual(response_put.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Intentar PATCH -> 405 Method Not Allowed
        response_patch = self.client.patch(
            f"/api/familias/miembros/{rel.id_familia_usuario}/",
            {"estado": False},
            format="json",
        )
        self.assertEqual(response_patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_list_miembros_filtrado_por_familia_exito(self):
        """Valida el listado correcto filtrado por una familia existente."""
        familia = Familia.objects.create(nombre_familia="Familia Filtro")
        rel1 = FamiliaUsuario.objects.create(fk_usuario=self.usuario_cliente1, fk_familia=familia, estado=True)
        rel2 = FamiliaUsuario.objects.create(fk_usuario=self.usuario_cliente2, fk_familia=familia, estado=True)

        response = self.client.get(
            "/api/familias/miembros/",
            {"fk_familia": familia.id_familia},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)
        ids = [item["id_familia_usuario"] for item in response.data["results"]]
        self.assertIn(rel1.id_familia_usuario, ids)
        self.assertIn(rel2.id_familia_usuario, ids)

    def test_list_miembros_invalid_familia_id_format(self):
        """Valida que pasar un fk_familia no numérico devuelva error 400."""
        response = self.client.get(
            "/api/familias/miembros/",
            {"fk_familia": "no-numerico"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_familia", response.data)

    def test_list_miembros_nonexistent_or_inactive_familia(self):
        """Valida que pasar un fk_familia inexistente o inactivo devuelva error 400."""
        response1 = self.client.get(
            "/api/familias/miembros/",
            {"fk_familia": 99999},
            format="json",
        )
        self.assertEqual(response1.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_familia", response1.data)

        familia_inactiva = Familia.objects.create(nombre_familia="Familia Inactiva", estado=False)
        response2 = self.client.get(
            "/api/familias/miembros/",
            {"fk_familia": familia_inactiva.id_familia},
            format="json",
        )
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fk_familia", response2.data)

    def test_papelera_familias_exito(self):
        """Valida que una familia inactiva aparezca en la papelera y no en la lista activa."""
        Familia.objects.create(nombre_familia="Familia Activa", estado=True)
        Familia.objects.create(nombre_familia="Familia Inactiva", estado=False)

        # Listar activas
        response_activa = self.client.get("/api/familias/grupos/", format="json")
        self.assertEqual(response_activa.status_code, status.HTTP_200_OK)
        nombres_activos = [f["nombre_familia"] for f in response_activa.data["results"]]
        self.assertIn("Familia Activa", nombres_activos)
        self.assertNotIn("Familia Inactiva", nombres_activos)

        # Listar papelera
        response_trash = self.client.get("/api/familias/grupos/trash/", format="json")
        self.assertEqual(response_trash.status_code, status.HTTP_200_OK)
        nombres_trash = [f["nombre_familia"] for f in response_trash.data["results"]]
        self.assertNotIn("Familia Activa", nombres_trash)
        self.assertIn("Familia Inactiva", nombres_trash)

    def test_restaurar_familia_exito(self):
        """Valida la restauración de una familia inactiva y de sus miembros."""
        familia = Familia.objects.create(nombre_familia="Familia Inactiva", estado=False)
        miembro = FamiliaUsuario.objects.create(fk_usuario=self.usuario_cliente1, fk_familia=familia, estado=False)

        response = self.client.post(f"/api/familias/grupos/{familia.id_familia}/restore/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verificar estado restaurado
        familia.refresh_from_db()
        miembro.refresh_from_db()
        self.assertTrue(familia.estado)
        self.assertTrue(miembro.estado)

    def test_eliminacion_permanente_familia_exito(self):
        """Valida la eliminación física definitiva de una familia inactiva."""
        familia = Familia.objects.create(nombre_familia="Familia Inactiva", estado=False)
        miembro = FamiliaUsuario.objects.create(fk_usuario=self.usuario_cliente1, fk_familia=familia, estado=False)

        response = self.client.post(f"/api/familias/grupos/{familia.id_familia}/permanent/", format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verificar eliminación de la DB
        self.assertFalse(Familia.objects.filter(id_familia=familia.id_familia).exists())
        self.assertFalse(FamiliaUsuario.objects.filter(id_familia_usuario=miembro.id_familia_usuario).exists())
