import logging

from .models import ActivityLog

logger = logging.getLogger(__name__)


class ActivityLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            try:
                ActivityLog.objects.create(
                    user=request.user if getattr(request.user, "is_authenticated", False) else None,
                    action=f"{request.method} {request.path}",
                    ip_address=self._get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                    method=request.method,
                    path=request.path,
                )
            except Exception:
                logger.exception("No se pudo registrar la actividad del usuario")

        return response

    def _get_client_ip(self, request):
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")
