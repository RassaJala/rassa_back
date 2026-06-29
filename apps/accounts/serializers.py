from django.contrib.auth.hashers import make_password
from django.db import connection
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Role


def dictfetchall(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_user_data_dict(user_id):
    sql = """
        SELECT
            u.id_usuario AS id,
            u.correo AS email,
            u.telefono AS phone_number,
            r.nombre_rol AS role,
            p.nombre AS first_name,
            p.apellido_paterno AS last_name
        FROM usuario u
        INNER JOIN persona p ON u.fk_persona = p.id_persona
        INNER JOIN roles r ON u.fk_rol = r.id_rol
        WHERE u.id_usuario = %s
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [user_id])
        rows = dictfetchall(cursor)
    return rows[0] if rows else None


def get_user_list_data():
    sql = """
        SELECT
            u.id_usuario AS id,
            u.correo AS email,
            u.telefono AS phone_number,
            r.nombre_rol AS role,
            p.nombre AS first_name,
            p.apellido_paterno AS last_name
        FROM usuario u
        INNER JOIN persona p ON u.fk_persona = p.id_persona
        INNER JOIN roles r ON u.fk_rol = r.id_rol
        ORDER BY u.id_usuario
    """
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return dictfetchall(cursor)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = 'correo'

    def validate(self, attrs):
        if self.username_field not in attrs and "username" in attrs:
            attrs[self.username_field] = attrs["username"]
        return super().validate(attrs)


class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    phone_number = serializers.CharField(allow_blank=True, default="")
    role = serializers.CharField()
    first_name = serializers.CharField(allow_blank=True, default="")
    last_name = serializers.CharField(allow_blank=True, default="")


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ("id_rol", "nombre_rol", "descripcion", "creado_en", "estado")
        read_only_fields = ("id_rol", "creado_en")


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    phone_number = serializers.CharField(required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(
        choices=["buyer", "farmer", "admin"],
        required=False,
        default="buyer",
    )
    first_name = serializers.CharField(required=False, allow_blank=True, default="")
    last_name = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_email(self, value):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM usuario WHERE correo = %s LIMIT 1", [value])
            if cursor.fetchone():
                raise serializers.ValidationError("Este correo ya está registrado.")
        return value

    def create(self, validated_data):
        email = validated_data["email"]
        password = validated_data["password"]
        phone_number = validated_data.get("phone_number", "")
        role_name = validated_data.get("role", "buyer")
        first_name = validated_data.get("first_name", "")
        last_name = validated_data.get("last_name", "")

        hashed = make_password(password)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id_rol FROM roles WHERE nombre_rol = %s",
                [role_name],
            )
            row = cursor.fetchone()
            if not row:
                raise serializers.ValidationError(f"Rol '{role_name}' no válido.")
            role_id = row[0]

            cursor.execute(
                """INSERT INTO persona
                   (nombre, apellido_paterno, apellido_materno, fecha_nacimiento, sexo, domicilio, fk_localidad, estado)
                   VALUES (%s, %s, '', '2000-01-01', 'O', 'Sin especificar', NULL, TRUE)
                   RETURNING id_persona""",
                [first_name or "Usuario", last_name or ""],
            )
            persona_id = cursor.fetchone()[0]

            cursor.execute(
                """INSERT INTO usuario
                   (fk_persona, telefono, contrasenia, correo, fk_rol, estado)
                   VALUES (%s, %s, %s, %s, %s, TRUE)
                   RETURNING id_usuario""",
                [persona_id, phone_number, hashed, email, role_id],
            )
            user_id = cursor.fetchone()[0]

        data = get_user_data_dict(user_id)
        if data is None:
            raise serializers.ValidationError("Error al crear el usuario.")
        return data


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    remember = serializers.BooleanField(default=False)
