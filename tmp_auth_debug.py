import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rassa.settings')
import django
django.setup()
from django.contrib.auth import get_user_model, authenticate
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()
print('USERNAME_FIELD=', User.USERNAME_FIELD)
print('REQUIRED_FIELDS=', User.REQUIRED_FIELDS)
print('User count=', User.objects.count())
print('Emails=', list(User.objects.values_list('email', flat=True)))
print('Staff count=', User.objects.filter(is_staff=True).count())
print('Admin exists=', User.objects.filter(email='admin@rassa.com').exists())
print('Authenticate admin@rassa.com with password 12345678:', authenticate(email='admin@rassa.com', password='12345678'))
print('TokenObtainPair username_field=', TokenObtainPairSerializer.username_field)
try:
    s = TokenObtainPairSerializer(data={'email': 'admin@rassa.com', 'password': '12345678'})
    print('Token serializer valid?', s.is_valid())
    print('Token serializer errors=', s.errors)
except Exception as exc:
    print('Token serializer exception:', repr(exc))
