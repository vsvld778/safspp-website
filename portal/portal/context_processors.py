from django.conf import settings
from .access import approved_organizations

def portal_context(request):
    return {
        "staging_mode": settings.PORTAL_INTAKE_MODE != "live",
        "intake_mode": settings.PORTAL_INTAKE_MODE,
        "registration_mode": settings.REGISTRATION_MODE,
        "operator_name": settings.PORTAL_OPERATOR_NAME,
        "policy_version": settings.PORTAL_POLICY_VERSION,
        "policy_url": settings.PORTAL_POLICY_URL,
        "public_site_url": settings.PUBLIC_SITE_URL,
        "has_partner_access": approved_organizations(request.user).exists(),
    }
