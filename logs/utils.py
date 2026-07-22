"""Utility functions for the logs app."""


def get_client_ip(request):
    """Extract client IP from request, respecting proxy headers.

    Checks X-Forwarded-For first (for reverse proxies), falls back to REMOTE_ADDR.
    Only trusts X-Forwarded-For if the direct peer is in TRUSTED_PROXIES.
    """
    from django.conf import settings

    trusted_proxies = getattr(settings, "TRUSTED_PROXIES", set())
    ip = request.META.get("HTTP_X_FORWARDED_FOR")
    if ip:
        client_ip = ip.split(",")[0].strip()
        remote_addr = request.META.get("REMOTE_ADDR", "")
        if not trusted_proxies or remote_addr in trusted_proxies:
            return client_ip
    return request.META.get("REMOTE_ADDR", "0.0.0.0")
