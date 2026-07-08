from .models import ActivityLog

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

        if request.method in RELEVANT_METHODS:
            user = request.user if getattr(request.user, "is_authenticated", False) else None
            ActivityLog.objects.create(
                user=user,
                action=ACTION_BY_METHOD[request.method],
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                http_method=request.method,
                path=request.path,
            )

        return response
