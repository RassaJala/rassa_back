from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import ActivityLog


class ActivityLogModelTests(TestCase):
    def test_create_activity_log_with_required_fields(self):
        user = get_user_model().objects.create_user(username="tester", password="secret123")

        log = ActivityLog.objects.create(
            user=user,
            action="login",
            ip_address="127.0.0.1",
            user_agent="test-agent",
            http_method="GET",
            path="/api/auth/me/",
        )

        self.assertEqual(log.user, user)
        self.assertEqual(log.action, "login")
        self.assertEqual(log.ip_address, "127.0.0.1")
        self.assertEqual(log.http_method, "GET")
        self.assertEqual(log.path, "/api/auth/me/")
        self.assertIsNotNone(log.timestamp)
