from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from django.urls import reverse

from .models import ActivityLog


class ActivityLogModelTests(TestCase):
    def test_create_activity_log(self):
        user = get_user_model().objects.create_user(username="tester", password="secret123")

        log = ActivityLog.objects.create(
            user=user,
            action="login",
            ip_address="127.0.0.1",
            user_agent="Mozilla/5.0",
            method="GET",
            path="/api/health/",
        )

        self.assertEqual(log.user, user)
        self.assertEqual(log.action, "login")
        self.assertEqual(log.ip_address, "127.0.0.1")
        self.assertEqual(log.method, "GET")
        self.assertEqual(log.path, "/api/health/")
        self.assertIsNotNone(log.timestamp)

    def test_relevant_http_methods_are_logged(self):
        methods = ["POST", "PUT", "PATCH", "DELETE"]

        for method in methods:
            with self.subTest(method=method):
                ActivityLog.objects.all().delete()

                if method == "POST":
                    self.client.post("/api/token/", data={"username": "tester", "password": "secret123"})
                else:
                    self.client.generic(method, "/api/token/", data={}, content_type="application/json")

                self.assertTrue(ActivityLog.objects.filter(method=method).exists())
                log = ActivityLog.objects.filter(method=method).latest("timestamp")
                self.assertEqual(log.path, "/api/token/")
                self.assertIn(method, log.action)


class ActivityLogViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = get_user_model().objects.create_user(
            username="admin",
            password="secret123",
            is_staff=True,
        )
        self.regular_user = get_user_model().objects.create_user(
            username="viewer",
            password="secret123",
        )

        ActivityLog.objects.create(user=self.admin_user, action="login", method="POST", path="/api/token/")
        ActivityLog.objects.create(user=self.regular_user, action="view report", method="GET", path="/api/reports/")
        ActivityLog.objects.create(user=self.admin_user, action="export data", method="GET", path="/api/export/")

    def test_admin_can_list_logs_with_filters(self):
        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(
            reverse("logs:list"),
            {"user": self.admin_user.id, "date": "2026-07-04", "action": "login"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["action"], "login")
        self.assertEqual(response.data["results"][0]["user"], self.admin_user.id)

    def test_non_admin_cannot_list_logs(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get(reverse("logs:list"))

        self.assertEqual(response.status_code, 403)
