from django.urls import path

from .views import MensajeCreateView, MensajeDocumentoCreateView, MensajeLeerView, MensajeListView, MensajeUpdateView

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
    path(
        "api/chat/mensajes/<int:mensaje_id>/editar/",
        MensajeUpdateView.as_view(),
        name="chat-mensajes-editar",
    ),
    path(
        "api/chat/mensajes/<int:mensaje_id>/leer/",
        MensajeLeerView.as_view(),
        name="chat-mensajes-leer",
    ),
    path(
        "api/chat/mensajes/enviar-con-documento/",
        MensajeDocumentoCreateView.as_view(),
        name="chat-mensajes-enviar-con-documento",
    ),
]
