from .models import Organization, SupportCase

def approved_organizations(user):
    if not user.is_authenticated:
        return Organization.objects.none()
    return Organization.objects.filter(is_approved=True, memberships__user=user, memberships__is_active=True)

def partner_cases(user):
    return SupportCase.objects.filter(partner_organization__in=approved_organizations(user), partner_sharing_approved=True).exclude(partner_consent_record="").exclude(partner_summary="")
