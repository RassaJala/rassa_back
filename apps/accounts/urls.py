from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login-api/", views.LoginApiView.as_view(), name="login-api"),
    path("users/", views.UserListView.as_view(), name="user-list"),
    path("roles/", views.RoleListView.as_view(), name="role-list"),
    path("me/", views.MeView.as_view(), name="me"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
]
