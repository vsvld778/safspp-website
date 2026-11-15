from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand
from django.utils import timezone
from portal.models import RateLimitBucket

class Command(BaseCommand):
    help = "Remove expired throttle counters and sessions; never delete cases/messages."

    def handle(self, *args, **options):
        buckets, _ = RateLimitBucket.objects.filter(expires_at__lt=timezone.now()).delete()
        sessions, _ = Session.objects.filter(expire_date__lt=timezone.now()).delete()
        self.stdout.write(f"Expired rate-limit rows: {buckets}; expired sessions: {sessions}.")
