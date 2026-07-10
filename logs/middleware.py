import logging

from django.conf import settings

from rassa.models import Log, Usuario

from .utils import get_client_ip

logger = logging.getLogger(__name__)

RELEVANT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
ACTION_BY_METHOD = {
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}


class ActivityLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        excluded_paths = getattr(settings, "EXCLUDED_PATHS", [])
        if (
            request.method in RELEVANT_METHODS
            and getattr(request.user, "is_authenticated", False)
            and not any(request.path.startswith(p) for p in excluded_paths)
        ):
            try:
                usuario = Usuario.objects.filter(fk_user=request.user).first()
                action = ACTION_BY_METHOD[request.method]
                qs = request.META.get("QUERY_STRING", "")
                descripcion = f"{action} {request.method} {request.path}"
                if qs:
                    descripcion += f"?{qs}"
                Log.objects.create(
                    fk_usuario=usuario,
                    descripcion=descripcion,
                    ip=get_client_ip(request),
                    dispositivo=request.META.get("HTTP_USER_AGENT", ""),
                )
            except Exception as exc:
                logger.warning("Error al guardar log: %s", exc)

        return response
