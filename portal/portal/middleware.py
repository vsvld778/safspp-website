import ipaddress
from django.conf import settings
from django.utils.cache import patch_cache_control

class TrustedProxyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Gunicorn must only listen on localhost. Nginx must overwrite these headers.
        if settings.TRUST_PROXY_HEADERS and request.META.get("REMOTE_ADDR") in {"127.0.0.1", "::1"}:
            value = request.META.get("HTTP_X_REAL_IP", "")
            try:
                request.META["REMOTE_ADDR"] = str(ipaddress.ip_address(value))
            except ValueError:
                pass
        return self.get_response(request)

class PrivateResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/static/"):
            patch_cache_control(response, private=True, no_store=True, no_cache=True, must_revalidate=True)
            response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if not request.path.startswith("/admin/"):
            response["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response
