"""Tests for auth serializer extraction from apps.accounts to rassa.

Per spec: Spanish error messages preserved, User import changed to
django.contrib.auth.models.User, username_field explicitly set to "email"
since default User model uses "username" as USERNAME_FIELD.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework_simplejwt.exceptions import InvalidToken

from rassa.auth_serializers import CustomTokenObtainPairSerializer

User = get_user_model()


class CustomTokenObtainPairSerializerTest(TestCase):
    """Verify the extracted serializer works with django.contrib.auth.models.User
    and returns Spanish error messages as specified.
    """

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="test@rassa.com",
            email="test@rassa.com",
            password="correct-password",
        )
        self.serializer = CustomTokenObtainPairSerializer()

    def test_import_source_is_rassa(self) -> None:
        """Serializer must be importable from rassa.auth_serializers."""
        self.assertEqual(
            CustomTokenObtainPairSerializer.__module__,
            "rassa.auth_serializers",
        )

    def test_username_field_is_email(self) -> None:
        """Serializer must have username_field="email" so clients send {"email": ...}."""
        self.assertEqual(CustomTokenObtainPairSerializer.username_field, "email")

    def test_nonexistent_email_spanish_error(self) -> None:
        """Non-existent email must raise with Spanish error (ambiguous)."""
        attrs = {"email": "no-existe@rassa.com", "password": "irrelevant"}
        with self.assertRaises(InvalidToken) as ctx:
            self.serializer.validate(attrs)
        self.assertIn(
            "Correo electrónico o contraseña inválidos.",
            str(ctx.exception),
        )

    def test_wrong_password_spanish_error(self) -> None:
        """Wrong password must raise with Spanish error (ambiguous)."""
        attrs = {"email": "test@rassa.com", "password": "wrong-password"}
        with self.assertRaises(InvalidToken) as ctx:
            self.serializer.validate(attrs)
        self.assertIn(
            "Correo electrónico o contraseña inválidos.",
            str(ctx.exception),
        )

    def test_inactive_user_spanish_error(self) -> None:
        """Inactive user must raise same ambiguous error as nonexistent email."""
        self.user.is_active = False
        self.user.save()
        attrs = {"email": "test@rassa.com", "password": "correct-password"}
        with self.assertRaises(InvalidToken) as ctx:
            self.serializer.validate(attrs)
        self.assertIn(
            "Correo electrónico o contraseña inválidos.",
            str(ctx.exception),
        )

    def test_valid_credentials_returns_tokens(self) -> None:
        """Valid credentials must return access and refresh tokens."""
        attrs = {"email": "test@rassa.com", "password": "correct-password"}
        result = self.serializer.validate(attrs)
        self.assertIn("access", result)
        self.assertIn("refresh", result)
        self.assertIsInstance(result["access"], str)
        self.assertIsInstance(result["refresh"], str)
