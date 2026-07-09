from django.conf import settings

from rassa.models import Log, Usuario

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
        if (
            request.method in RELEVANT_METHODS
            and getattr(request.user, "is_authenticated", False)
            and not any(request.path.startswith(p) for p in self.excluded_paths)
        ):
            usuario = Usuario.objects.filter(fk_user=request.user).first()
            action = ACTION_BY_METHOD[request.method]
            qs = request.META.get("QUERY_STRING", "")
            descripcion = f"{action} {request.method} {request.path}"
            if qs:
                descripcion += f"?{qs}"
            Log.objects.create(
                fk_usuario=usuario,
                descripcion=descripcion,
                ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
                dispositivo=request.META.get("HTTP_USER_AGENT", ""),
            )

        return self.get_response(request)
