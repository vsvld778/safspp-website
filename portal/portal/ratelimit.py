"""Database-backed fixed windows, shared across Gunicorn workers. No raw IP/email stored."""
import hashlib
import hmac
import time
from datetime import datetime, timezone
from django.conf import settings
from django.db.models import F
from .models import RateLimitBucket

def allow_request(scope, principal, limit, seconds):
    window = int(time.time()) // seconds
    data = f"{scope}:{principal}:{window}".encode()
    key = hmac.new(settings.SECRET_KEY.encode(), data, hashlib.sha256).hexdigest()
    bucket, _ = RateLimitBucket.objects.get_or_create(key=key, defaults={
        "expires_at": datetime.fromtimestamp((window + 1) * seconds, tz=timezone.utc)})
    RateLimitBucket.objects.filter(pk=bucket.pk).update(count=F("count") + 1)
    bucket.refresh_from_db(fields=["count"])
    return bucket.count <= limit

def client_ip(request):
    return request.META.get("REMOTE_ADDR", "unknown")
