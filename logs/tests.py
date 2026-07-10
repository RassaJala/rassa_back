from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from rassa.models import Log, Persona, Rol, Usuario


def _create_test_user(rol_name="Admin"):
    user = get_user_model().objects.create_user(username="tester", email="tester@email.com", password="secret123")
    rol, _ = Rol.objects.get_or_create(nombre_rol=rol_name, defaults={"descripcion": f"{rol_name} test"})
    persona = Persona.objects.create(
        nombre="Test",
        apellido_paterno="User",
        fecha_nacimiento="2000-01-01",
        sexo="M",
        domicilio="Calle 123",
    )
    usuario = Usuario.objects.create(
        fk_user=user,
        fk_persona=persona,
        telefono="4610000000",
        correo="tester@email.com",
        fk_rol=rol,
    )
    return user, usuario


class LogModelTest(TestCase):
    def test_create_log(self):
        _, usuario = _create_test_user()
        log = Log.objects.create(
            fk_usuario=usuario,
            descripcion="create POST /api/test/",
            ip="127.0.0.1",
            dispositivo="test-agent",
        )
        self.assertEqual(log.fk_usuario, usuario)
        self.assertIn("create", log.descripcion)
        self.assertEqual(log.ip, "127.0.0.1")
        self.assertEqual(log.dispositivo, "test-agent")
        self.assertIsNotNone(log.creado_en)


class ActivityLogMiddlewareTest(TestCase):
    def setUp(self):
        self.user, self.usuario = _create_test_user()
        self.factory = RequestFactory()

    def test_logs_authenticated_post(self):
        request = self.factory.post("/api/alguna/")
        request.user = self.user
        from logs.middleware import ActivityLogMiddleware

        middleware = ActivityLogMiddleware(lambda req: type("Resp", (), {})())
        middleware(request)

        self.assertEqual(Log.objects.count(), 1)
        log = Log.objects.first()
        self.assertEqual(log.fk_usuario, self.usuario)
        self.assertIn("POST", log.descripcion)

    def test_skips_get_requests(self):
        request = self.factory.get("/api/alguna/")
        request.user = self.user
        from logs.middleware import ActivityLogMiddleware

        middleware = ActivityLogMiddleware(lambda req: type("Resp", (), {})())
        middleware(request)

        self.assertEqual(Log.objects.count(), 0)

    def test_skips_anonymous_user(self):
        request = self.factory.post("/api/alguna/")
        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()
        from logs.middleware import ActivityLogMiddleware

        middleware = ActivityLogMiddleware(lambda req: type("Resp", (), {})())
        middleware(request)

        self.assertEqual(Log.objects.count(), 0)

    def test_skips_excluded_paths(self):
        request = self.factory.post("/admin/algo/")
        request.user = self.user
        from logs.middleware import ActivityLogMiddleware

        middleware = ActivityLogMiddleware(lambda req: type("Resp", (), {})())
        middleware(request)

        self.assertEqual(Log.objects.count(), 0)

    @patch("logs.middleware.Log.objects.create")
    def test_db_failure_does_not_break_request(self, mock_create):
        mock_create.side_effect = Exception("DB fallo")
        request = self.factory.post("/api/alguna/")
        request.user = self.user
        from logs.middleware import ActivityLogMiddleware

        response = object()
        middleware = ActivityLogMiddleware(lambda req: response)
        with self.assertLogs("logs.middleware", level="WARNING"):
            result = middleware(request)
        self.assertIs(result, response)


class IsAdminPermissionTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_admin_has_access(self):
        user, _ = _create_test_user("Admin")
        request = self.factory.get("/api/logs/")
        request.user = user
        from logs.views import IsAdmin

        self.assertTrue(IsAdmin().has_permission(request, None))

    def test_non_admin_denied(self):
        user, _ = _create_test_user("Cliente")
        request = self.factory.get("/api/logs/")
        request.user = user
        from logs.views import IsAdmin

        self.assertFalse(IsAdmin().has_permission(request, None))

    def test_anonymous_denied(self):
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get("/api/logs/")
        request.user = AnonymousUser()
        from logs.views import IsAdmin

        self.assertFalse(IsAdmin().has_permission(request, None))


class AuthMeEndpointTest(TestCase):
    def setUp(self):
        self.user, self.usuario = _create_test_user()
        self.factory = APIRequestFactory()

    def test_get_returns_user_data(self):
        request = self.factory.get("/api/auth/me/")
        force_authenticate(request, user=self.user)
        from rassa.urls import auth_me

        response = auth_me(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "tester@email.com")
        self.assertEqual(response.data["id_usuario"], self.usuario.id_usuario)

    def test_patch_updates_profile(self):
        request = self.factory.patch(
            "/api/auth/me/",
            {"nombre": "Nuevo", "apellidos": "Nombre"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        from rassa.urls import auth_me

        response = auth_me(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["nombre"], "Nuevo")
        self.assertEqual(response.data["apellidos"], "Nombre")


class LoginLogTest(TestCase):
    def setUp(self):
        self.user, self.usuario = _create_test_user()
        self.factory = APIRequestFactory()

    def test_login_creates_log(self):
        from rassa.urls import CustomTokenObtainPairView

        data = {"email": "tester@email.com", "password": "secret123"}
        request = self.factory.post("/api/token/", data, format="json")
        request.user = type("Anon", (), {"is_authenticated": property(lambda self: False)})()

        view = CustomTokenObtainPairView.as_view()
        response = view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        log = Log.objects.filter(descripcion="login POST /api/token/").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.fk_usuario, self.usuario)

    def test_failed_login_logs_attempt(self):
        from rassa.urls import CustomTokenObtainPairView

        data = {"email": "tester@email.com", "password": "wrongpass"}
        request = self.factory.post("/api/token/", data, format="json")
        request.user = type("Anon", (), {"is_authenticated": property(lambda self: False)})()

        view = CustomTokenObtainPairView.as_view()
        response = view(request)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        log = Log.objects.filter(descripcion__startswith="login_fallido").first()
        self.assertIsNotNone(log)
        self.assertIn("tester@email.com", log.descripcion)
        self.assertIsNone(log.fk_usuario)
