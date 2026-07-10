"""Utility functions for the logs app."""


def get_client_ip(request):
    """Extract client IP from request, respecting proxy headers.

    Checks X-Forwarded-For first (for reverse proxies), falls back to REMOTE_ADDR.
    """
    ip = request.META.get("HTTP_X_FORWARDED_FOR")
    if ip:
        return ip.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")
