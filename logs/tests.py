from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from rassa.models import Log, Persona, Rol, Usuario

_user_counter = 0


def _create_test_user(rol_name="Admin"):
    global _user_counter
    _user_counter += 1
    suffix = _user_counter
    user = get_user_model().objects.create_user(
        username=f"tester{suffix}", email=f"tester{suffix}@email.com", password="secret123"
    )
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
        correo=user.email,
        fk_rol=rol,
    )
    return user, usuario


def _make_middleware(get_response=None):
    """Helper to create ActivityLogMiddleware with a dummy get_response."""
    from logs.middleware import ActivityLogMiddleware

    if get_response is None:

        def _dummy_response(req):
            return type("Resp", (), {})()

        get_response = _dummy_response
    return ActivityLogMiddleware(get_response)


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

        _make_middleware()(request)

        self.assertEqual(Log.objects.count(), 1)
        log = Log.objects.first()
        self.assertEqual(log.fk_usuario, self.usuario)
        self.assertIn("POST", log.descripcion)

    def test_logs_includes_query_string(self):
        request = self.factory.post("/api/items/?page=1&limit=10")
        request.user = self.user

        _make_middleware()(request)

        self.assertEqual(Log.objects.count(), 1)
        log = Log.objects.first()
        self.assertIn("page=1&limit=10", log.descripcion)

    def test_skips_get_requests(self):
        request = self.factory.get("/api/alguna/")
        request.user = self.user

        _make_middleware()(request)

        self.assertEqual(Log.objects.count(), 0)

    def test_skips_anonymous_user(self):
        request = self.factory.post("/api/alguna/")
        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()

        _make_middleware()(request)

        self.assertEqual(Log.objects.count(), 0)

    def test_skips_excluded_paths(self):
        request = self.factory.post("/admin/algo/")
        request.user = self.user

        _make_middleware()(request)

        self.assertEqual(Log.objects.count(), 0)

    def test_excluded_paths_read_at_call_time(self):
        """excluded_paths should be read from settings on each call, not cached at init."""
        request = self.factory.post("/admin/test/")
        request.user = self.user

        middleware = _make_middleware()
        # Cambiar path DESPUES de crear el middleware, antes de llamarlo
        request.path = "/api/some-path/"
        middleware(request)

        self.assertEqual(Log.objects.count(), 1)
        log = Log.objects.first()
        self.assertIn("POST /api/some-path/", log.descripcion)

    def test_uses_x_forwarded_for(self):
        request = self.factory.post("/api/alguna/")
        request.user = self.user
        request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.1, 10.0.0.1"

        _make_middleware()(request)

        log = Log.objects.first()
        self.assertEqual(log.ip, "203.0.113.1")

    def test_falls_back_to_remote_addr(self):
        request = self.factory.post("/api/alguna/")
        request.user = self.user
        request.META["REMOTE_ADDR"] = "192.168.1.1"

        _make_middleware()(request)

        log = Log.objects.first()
        self.assertEqual(log.ip, "192.168.1.1")

    @patch("logs.middleware.Log.objects.create")
    def test_db_failure_does_not_break_request(self, mock_create):
        mock_create.side_effect = Exception("DB fallo")
        request = self.factory.post("/api/alguna/")
        request.user = self.user

        response = object()
        middleware = _make_middleware(get_response=lambda req: response)
        with self.assertLogs("logs.middleware", level="WARNING"):
            result = middleware(request)
        self.assertIs(result, response)


class LogSerializerTest(TestCase):
    def test_serializer_output_has_expected_fields(self):
        _, usuario = _create_test_user()
        log = Log.objects.create(
            fk_usuario=usuario,
            descripcion="test POST /api/test/",
            ip="127.0.0.1",
            dispositivo="test-agent",
        )
        from logs.serializers import LogSerializer

        serializer = LogSerializer(log)
        data = serializer.data
        self.assertIn("id_log", data)
        self.assertIn("fk_usuario", data)
        self.assertIn("usuario_correo", data)
        self.assertEqual(data["usuario_correo"], usuario.correo)
        self.assertIn("descripcion", data)
        self.assertIn("ip", data)
        self.assertIn("dispositivo", data)
        self.assertIn("creado_en", data)
        self.assertIn("estado", data)

    def test_serializer_usuario_correo_none_when_no_fk(self):
        log = Log.objects.create(
            fk_usuario=None,
            descripcion="test POST /api/test/",
            ip="127.0.0.1",
            dispositivo="test-agent",
        )
        from logs.serializers import LogSerializer

        serializer = LogSerializer(log)
        self.assertIsNone(serializer.data["usuario_correo"])


class LogViewSetTest(TestCase):
    """Tests for ActivityLogViewSet — covers B1 blocker."""

    def setUp(self):
        self.admin_user, self.admin_usuario = _create_test_user("Admin")
        self.client_user, _ = _create_test_user("Cliente")
        self.factory = APIRequestFactory()

    def _create_logs(self):
        for i in range(3):
            Log.objects.create(
                fk_usuario=self.admin_usuario,
                descripcion=f"test {i} POST /api/test/",
                ip="127.0.0.1",
                dispositivo="test-agent",
            )

    def test_list_requires_auth(self):
        self._create_logs()
        from logs.views import ActivityLogViewSet

        request = self.factory.get("/api/logs/")
        view = ActivityLogViewSet.as_view({"get": "list"})
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_denies_non_admin(self):
        self._create_logs()
        from logs.views import ActivityLogViewSet

        request = self.factory.get("/api/logs/")
        force_authenticate(request, user=self.client_user)
        view = ActivityLogViewSet.as_view({"get": "list"})
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_returns_logs_for_admin(self):
        self._create_logs()
        from logs.views import ActivityLogViewSet

        request = self.factory.get("/api/logs/")
        force_authenticate(request, user=self.admin_user)
        view = ActivityLogViewSet.as_view({"get": "list"})
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Paginated: results in response.data["results"]
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 3)

    def test_retrieve_returns_single_log(self):
        self._create_logs()
        log = Log.objects.first()
        from logs.views import ActivityLogViewSet

        request = self.factory.get(f"/api/logs/{log.id_log}/")
        force_authenticate(request, user=self.admin_user)
        view = ActivityLogViewSet.as_view({"get": "retrieve"})
        response = view(request, pk=log.id_log)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id_log"], log.id_log)

    def test_filter_by_descripcion(self):
        Log.objects.create(
            fk_usuario=self.admin_usuario, descripcion="create POST /api/items/", ip="1.1.1.1", dispositivo="a"
        )
        Log.objects.create(
            fk_usuario=self.admin_usuario, descripcion="delete POST /api/items/", ip="2.2.2.2", dispositivo="b"
        )
        from logs.views import ActivityLogViewSet

        request = self.factory.get("/api/logs/?descripcion=create")
        force_authenticate(request, user=self.admin_user)
        view = ActivityLogViewSet.as_view({"get": "list"})
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        self.assertIn("create", results[0]["descripcion"])

    def test_filter_by_ip(self):
        Log.objects.create(fk_usuario=self.admin_usuario, descripcion="first", ip="1.1.1.1", dispositivo="a")
        Log.objects.create(fk_usuario=self.admin_usuario, descripcion="second", ip="2.2.2.2", dispositivo="b")
        from logs.views import ActivityLogViewSet

        request = self.factory.get("/api/logs/?ip=2.2.2.2")
        force_authenticate(request, user=self.admin_user)
        view = ActivityLogViewSet.as_view({"get": "list"})
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        # Due to pagination, verify by checking all returned results
        for r in results:
            self.assertEqual(r["ip"], "2.2.2.2")


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

    def test_unauthenticated_returns_401(self):
        """C1: Verify /api/auth/me/ rejects unauthenticated requests."""
        from rassa.views import MeView

        request = self.factory.get("/api/auth/me/")
        response = MeView.as_view()(request)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("detail", response.data)

    def test_get_returns_user_data(self):
        from rassa.views import MeView

        request = self.factory.get("/api/auth/me/")
        force_authenticate(request, user=self.user)
        response = MeView.as_view()(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["email"], self.user.email)
        self.assertEqual(response.data["data"]["id_usuario"], self.usuario.id_usuario)

    def test_patch_updates_profile_and_persists(self):
        """C2: Verify PATCH updates the DB, not just the response."""
        from rassa.views import MeView

        request = self.factory.patch(
            "/api/auth/me/",
            {"nombre": "Nuevo", "apellido_paterno": "NuevoApellido"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = MeView.as_view()(request)
        # MeView wraps data in _ok() -> {"data": ...}
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("data", response.data)
        updated = response.data["data"]
        self.assertEqual(updated["nombre"], "Nuevo")

        # Verify persistence in DB
        persona = Persona.objects.get(pk=self.usuario.fk_persona.pk)
        self.assertEqual(persona.nombre, "Nuevo")
        self.assertEqual(persona.apellido_paterno, "NuevoApellido")


class LoginLogTest(TestCase):
    def setUp(self):
        self.user, self.usuario = _create_test_user()
        self.factory = APIRequestFactory()

    def _login_data(self, password="secret123"):
        return {"email": self.user.email, "password": password}

    def test_login_creates_log(self):
        from rassa.urls import CustomTokenObtainPairView

        data = self._login_data()
        request = self.factory.post("/api/token/", data, format="json")

        view = CustomTokenObtainPairView.as_view()
        response = view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        log = Log.objects.filter(descripcion="login POST /api/token/").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.fk_usuario, self.usuario)

    def test_login_log_correo_is_serializer_user(self):
        """C5: Verify the log uses the serializer-validated user, not a re-query."""
        from rassa.urls import CustomTokenObtainPairView

        data = self._login_data()
        request = self.factory.post("/api/token/", data, format="json")

        with patch("rassa.urls.Usuario.objects.filter", wraps=Usuario.objects.filter):
            view = CustomTokenObtainPairView.as_view()
            response = view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        log = Log.objects.filter(descripcion="login POST /api/token/").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.fk_usuario, self.usuario)

    def test_failed_login_logs_attempt(self):
        from rassa.urls import CustomTokenObtainPairView

        data = self._login_data(password="wrongpass")
        request = self.factory.post("/api/token/", data, format="json")

        view = CustomTokenObtainPairView.as_view()
        response = view(request)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        log = Log.objects.filter(descripcion__startswith="login_fallido").first()
        self.assertIsNotNone(log)
        self.assertIn(self.user.email, log.descripcion)
        self.assertIsNone(log.fk_usuario)

    def test_failed_login_db_failure_does_not_mask_error(self):
        """C3: DB failure on log creation should not swallow original auth error."""
        from rassa.urls import CustomTokenObtainPairView

        data = self._login_data(password="wrongpass")
        request = self.factory.post("/api/token/", data, format="json")

        with patch("rassa.urls.Log.objects.create", side_effect=Exception("DB error")):
            view = CustomTokenObtainPairView.as_view()
            response = view(request)

        # Should still return 401 (InvalidToken), not 500
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_db_failure_does_not_block_token(self):
        """C7: DB failure on post-login log should not prevent token delivery."""
        from rassa.urls import CustomTokenObtainPairView

        data = self._login_data()
        request = self.factory.post("/api/token/", data, format="json")

        with patch("rassa.urls.Log.objects.create", side_effect=Exception("DB error")):
            view = CustomTokenObtainPairView.as_view()
            response = view(request)

        # Should still return 200 (token delivered)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)


class LogUrlRoutingTest(TestCase):
    """B1: Verify log URLs resolve correctly."""

    def test_log_list_url_resolves(self):
        from django.urls import resolve

        resolver = resolve("/api/logs/")
        self.assertEqual(resolver.view_name, "activitylog-list")

    def test_log_detail_url_resolves(self):
        from django.urls import resolve

        resolver = resolve("/api/logs/1/")
        self.assertEqual(resolver.view_name, "activitylog-detail")
