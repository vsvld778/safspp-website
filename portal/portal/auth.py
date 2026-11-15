from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied
from .ratelimit import allow_request, client_ip

class ThrottledEmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        email = (username or kwargs.get("email") or "").strip().casefold()
        if request is not None:
            ip_allowed = allow_request("login-ip", client_ip(request), 40, 900)
            account_allowed = allow_request("login-account", email, 12, 900)
            if not ip_allowed or not account_allowed:
                raise PermissionDenied("Authentication temporarily limited")
        return super().authenticate(request, username=email, password=password, **kwargs)
