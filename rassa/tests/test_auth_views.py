"""Tests for auth view extraction from apps.accounts to rassa.

Per spec: CustomTokenObtainPairView must import its serializer from
rassa.auth_serializers and be importable from rassa.auth_views.
"""

from django.test import TestCase

from rassa.auth_views import CustomTokenObtainPairView
from rassa.auth_serializers import CustomTokenObtainPairSerializer


class CustomTokenObtainPairViewTest(TestCase):
    """Verify the extracted view uses the correct serializer from rassa."""

    def test_import_source_is_rassa(self) -> None:
        """View must be importable from rassa.auth_views."""
        self.assertEqual(
            CustomTokenObtainPairView.__module__,
            "rassa.auth_views",
        )

    def test_serializer_class_is_from_rassa(self) -> None:
        """View must use CustomTokenObtainPairSerializer from rassa.auth_serializers."""
        self.assertIs(
            CustomTokenObtainPairView.serializer_class,
            CustomTokenObtainPairSerializer,
        )
