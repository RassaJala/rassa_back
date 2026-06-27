from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Role

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = User.USERNAME_FIELD

    def validate(self, attrs):
        if self.username_field not in attrs and "username" in attrs:
            attrs[self.username_field] = attrs["username"]
        return super().validate(attrs)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "phone_number", "role", "first_name", "last_name")
        read_only_fields = ("id",)


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ("id_rol", "nombre_rol", "descripcion", "creado_en", "estado")
        read_only_fields = ("id_rol", "creado_en")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("email", "password", "phone_number", "role", "first_name", "last_name")

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    remember = serializers.BooleanField(default=False)
