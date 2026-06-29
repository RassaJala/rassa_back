from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.hashers import check_password
from .models import User


class UsuarioAuthBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        email = kwargs.get('correo', username)
        if not email or not password:
            return None
        try:
            user = User.objects.get(correo=email, estado=True)
        except User.DoesNotExist:
            return None
        if not check_password(password, user.contrasenia):
            return None
        return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
