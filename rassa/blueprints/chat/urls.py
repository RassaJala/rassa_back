from django.urls import path

from .views import MensajeCreateView, MensajeListView

urlpatterns = [
    path(
        "api/chat/conversaciones/<int:conversacion_id>/mensajes/",
        MensajeListView.as_view(),
        name="chat-mensajes",
    ),
    path(
        "api/chat/mensajes/enviar/",
        MensajeCreateView.as_view(),
        name="chat-mensajes-enviar",
    ),
]
