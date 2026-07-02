"""Auth views extracted from apps.accounts.

CustomTokenObtainPairView imports its serializer from rassa.auth_serializers
to keep the auth logic within the rassa package after app deletion.
"""

from rest_framework_simplejwt.views import TokenObtainPairView

from rassa.auth_serializers import CustomTokenObtainPairSerializer


class CustomTokenObtainPairView(TokenObtainPairView):
    """Login with Spanish error messages."""

    serializer_class = CustomTokenObtainPairSerializer
