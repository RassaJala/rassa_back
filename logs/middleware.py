import logging

from django.conf import settings

from rassa.models import Log, Usuario

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
        self.excluded_paths = getattr(settings, "EXCLUDED_PATHS", [])

    def __call__(self, request):
        response = self.get_response(request)

        if (
            request.method in RELEVANT_METHODS
            and getattr(request.user, "is_authenticated", False)
            and not any(request.path.startswith(p) for p in self.excluded_paths)
        ):
            try:
                usuario = Usuario.objects.filter(fk_user=request.user).first()
                action = ACTION_BY_METHOD[request.method]
                qs = request.META.get("QUERY_STRING", "")
                descripcion = f"{action} {request.method} {request.path}"
                if qs:
                    descripcion += f"?{qs}"
                ip = request.META.get("HTTP_X_FORWARDED_FOR")
                if ip:
                    ip = ip.split(",")[0].strip()
                else:
                    ip = request.META.get("REMOTE_ADDR", "0.0.0.0")
                Log.objects.create(
                    fk_usuario=usuario,
                    descripcion=descripcion,
                    ip=ip,
                    dispositivo=request.META.get("HTTP_USER_AGENT", ""),
                )
            except Exception as exc:
                logger.warning("Error al guardar log: %s", exc)

        return response
