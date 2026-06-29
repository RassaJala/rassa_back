from django.urls import path
from . import views

urlpatterns = [
    path("conversaciones/<int:conversacion_id>/mensajes/", views.MensajesConversacionView.as_view(), name="mensajes-conversacion"),
    path("mensajes/enviar/", views.EnviarMensajeView.as_view(), name="enviar-mensaje"),
    path("mensajes/<int:mensaje_id>/editar/", views.EditarMensajeView.as_view(), name="editar-mensaje"),
    path("mensajes/<int:mensaje_id>/leer/", views.LeerMensajeView.as_view(), name="leer-mensaje"),
    path("mensajes/enviar-con-documento/", views.EnviarMensajeConDocumentoView.as_view(), name="enviar-mensaje-documento"),
    path("usuarios/<int:usuario_id>/conversaciones/", views.ConversacionesUsuarioView.as_view(), name="conversaciones-usuario"),
    path("conversaciones/crear-privada/", views.CrearConversacionPrivadaView.as_view(), name="crear-conversacion-privada"),
    path("conversaciones/crear-grupal/", views.CrearConversacionGrupalView.as_view(), name="crear-conversacion-grupal"),
    path("conversaciones/<int:conversacion_id>/agregar-integrante/", views.AgregarIntegranteView.as_view(), name="agregar-integrante"),
    path("mensajes/<int:mensaje_id>/inactivar/", views.InactivarMensajeView.as_view(), name="inactivar-mensaje"),
]
