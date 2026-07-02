"""Auth serializers extracted from apps.accounts.

Uses django.contrib.auth.models.User (not custom AUTH_USER_MODEL)
with username_field explicitly set to "email" since the default
Django User uses "username" as USERNAME_FIELD.

Spanish error messages preserved per spec LOG-5.
"""

from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Token serializer with Spanish error messages.

    Differentiates between nonexistent email and wrong password
    to return user-friendly Spanish messages (per spec LOG-5).

    username_field is explicitly set to "email" because the default
    Django User model uses "username" as USERNAME_FIELD. This keeps
    the API contract consistent: clients send {"email": ..., "password": ...}.
    """

    username_field = "email"

    def validate(self, attrs):
        email = attrs.get(self.username_field)
        password = attrs.get("password")

        user = User.objects.filter(email=email).first()

        if user is None:
            raise serializers.ValidationError(
                "No existe una cuenta con este correo.",
                code="authorization",
            )

        if not user.check_password(password):
            raise serializers.ValidationError(
                "Contraseña incorrecta.",
                code="authorization",
            )

        if not user.is_active:
            raise serializers.ValidationError(
                "No existe una cuenta con este correo.",
                code="authorization",
            )

        refresh = self.get_token(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }
