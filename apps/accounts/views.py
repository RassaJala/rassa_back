from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import make_password
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connection
from django.urls import reverse_lazy
from django.views.generic import FormView, RedirectView, TemplateView
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import Role
from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    MeUpdateSerializer,
    RoleSerializer,
    UserSerializer,
    RegisterSerializer,
    CustomTokenObtainPairSerializer,
    get_user_data_dict,
    get_user_list_data,
)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class LoginForm(forms.Form):
    email = forms.EmailField(label="Correo electrónico")
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput)


class LoginView(FormView):
    template_name = "accounts/login.html"
    form_class = LoginForm
    success_url = reverse_lazy("dashboard")

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password"]
        user = authenticate(self.request, correo=email, password=password)
        if user is None:
            form.add_error(None, "Credenciales incorrectas. Intenta de nuevo.")
            return self.form_invalid(form)
        if not user.is_active:
            form.add_error(None, "Esta cuenta está desactivada.")
            return self.form_invalid(form)
        login(self.request, user)
        messages.success(self.request, "Sesión iniciada correctamente.")
        return super().form_valid(form)


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user"] = self.request.user
        return context


class LogoutView(RedirectView):
    pattern_name = "login"

    def get(self, request, *args, **kwargs):
        logout(request)
        messages.success(request, "Has cerrado sesión correctamente.")
        return super().get(request, *args, **kwargs)


class RegisterView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_data = serializer.save()
        return Response(user_data, status=status.HTTP_201_CREATED)


class LoginApiView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]
        remember = serializer.validated_data["remember"]

        user = authenticate(request, correo=email, password=password)
        if user is None:
            return Response(
                {"success": False, "message": "Credenciales incorrectas."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not user.is_active:
            return Response(
                {"success": False, "message": "Esta cuenta está desactivada."},
                status=status.HTTP_403_FORBIDDEN,
            )

        login(request, user)
        if remember:
            request.session.set_expiry(1209600)
        else:
            request.session.set_expiry(0)

        refresh = RefreshToken.for_user(user)
        user_data = get_user_data_dict(user.id_usuario)

        return Response(
            {
                "success": True,
                "message": "Inicio de sesión correcto.",
                "remember": remember,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": user_data,
            },
            status=status.HTTP_200_OK,
        )


class UserListView(APIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        users = get_user_list_data()
        serializer = UserSerializer(data=users, many=True)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)


class RoleListView(generics.ListAPIView):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = (permissions.AllowAny,)


class MeView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        user_data = get_user_data_dict(request.user.id_usuario)
        if user_data is None:
            return Response(
                {"error": "Usuario no encontrado"},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = UserSerializer(data=user_data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)

    def patch(self, request):
        serializer = MeUpdateSerializer(data=request.data, user_id=request.user.id_usuario)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data.get("email")
        phone_number = serializer.validated_data.get("phone_number")
        first_name = serializer.validated_data.get("first_name")
        last_name = serializer.validated_data.get("last_name")

        with connection.cursor() as cursor:
            if email is not None:
                cursor.execute(
                    "UPDATE usuario SET correo = %s WHERE id_usuario = %s",
                    [email, request.user.id_usuario],
                )
            if phone_number is not None:
                cursor.execute(
                    "UPDATE usuario SET telefono = %s WHERE id_usuario = %s",
                    [phone_number, request.user.id_usuario],
                )
            if first_name is not None or last_name is not None:
                cursor.execute(
                    "SELECT fk_persona FROM usuario WHERE id_usuario = %s",
                    [request.user.id_usuario],
                )
                persona_id = cursor.fetchone()[0]
                if first_name is not None:
                    cursor.execute(
                        "UPDATE persona SET nombre = %s WHERE id_persona = %s",
                        [first_name, persona_id],
                    )
                if last_name is not None:
                    cursor.execute(
                        "UPDATE persona SET apellido_paterno = %s WHERE id_persona = %s",
                        [last_name, persona_id],
                    )

        user_data = get_user_data_dict(request.user.id_usuario)
        serializer = UserSerializer(data=user_data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)


class ChangePasswordView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, user=request.user)
        if not serializer.is_valid():
            errors = serializer.errors
            message = errors.get("current_password") or errors.get("non_field_errors") or errors
            return Response(
                {"success": False, "message": message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_password = serializer.validated_data["new_password"]
        hashed = make_password(new_password)

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE usuario SET contrasenia = %s WHERE id_usuario = %s",
                [hashed, request.user.id_usuario],
            )

        return Response({"success": True, "message": "Contraseña actualizada correctamente."})
