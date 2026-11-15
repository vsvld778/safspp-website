from django.contrib import admin
from django import forms
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.db import transaction
from django.utils import timezone
from .models import CaseEvent, CaseMessage, Organization, OrganizationMembership, SupportCase, User
from .organization_models import OrganizationEvent, OrganizationRequest, OrganizationRequestMessage, OrganizationWorkspace

class PortalAdminCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email", "display_name")

class PortalAdminChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"

@admin.register(User)
class PortalUserAdmin(UserAdmin):
    form = PortalAdminChangeForm
    add_form = PortalAdminCreationForm
    ordering = ("email",)
    list_display = ("email", "display_name", "is_active", "is_staff", "email_verified")
    search_fields = ("email", "display_name")
    fieldsets = ((None, {"fields": ("email", "password")}),
        ("Профиль", {"fields": ("display_name", "preferred_language", "email_verified")}),
        ("Права", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Даты", {"fields": ("last_login", "date_joined")}))
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "display_name", "password1", "password2")}),)
    readonly_fields = ("email_verified", "last_login", "date_joined")

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False

class SuperuserManagedAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Organization)
class OrganizationAdmin(SuperuserManagedAdmin):
    list_display = ("name", "kind", "is_approved")
    list_filter = ("is_approved", "kind")
    search_fields = ("name",)

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            OrganizationEvent.objects.create(organization=obj, actor=request.user,
                event_type="organization_updated" if change else "organization_created",
                detail={"fields": list(form.changed_data), "kind": obj.kind, "approved": obj.is_approved})

@admin.register(OrganizationMembership)
class MembershipAdmin(SuperuserManagedAdmin):
    list_display = ("organization", "user", "role", "is_active")
    list_filter = ("is_active", "role", "organization")
    autocomplete_fields = ("organization", "user")

    def save_model(self, request, obj, form, change):
        previous_org = OrganizationMembership.objects.filter(pk=obj.pk).values_list("organization_id", flat=True).first() if change else None
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            OrganizationEvent.objects.create(organization=obj.organization, actor=request.user,
                event_type="membership_updated", detail={"memberId": obj.user_id, "role": obj.role, "active": obj.is_active})
            if previous_org and previous_org != obj.organization_id:
                OrganizationEvent.objects.create(organization_id=previous_org, actor=request.user,
                    event_type="membership_removed", detail={"membershipId": obj.pk})

class CaseMessageInline(admin.TabularInline):
    model = CaseMessage
    fields = ("author", "audience", "partner_organization", "body", "created_at")
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

class CaseEventInline(admin.TabularInline):
    model = CaseEvent
    fields = ("created_at", "actor", "event_type", "detail")
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(SupportCase)
class SupportCaseAdmin(admin.ModelAdmin):
    list_display = ("reference", "title", "category", "status", "coordinator", "is_test", "updated_at")
    list_filter = ("status", "category", "is_test", "coordinator")
    search_fields = ("title", "owner__email", "owner__display_name")
    autocomplete_fields = ("partner_organization",)
    readonly_fields = ("reference", "public_id", "owner", "title", "category", "description", "city",
        "preferred_language", "is_test", "policy_version", "consented_at", "created_at", "updated_at")
    fieldsets = (("Обращение", {"fields": ("reference", "owner", "title", "category", "description", "city", "preferred_language", "is_test")}),
        ("Работа координатора", {"fields": ("status", "coordinator", "next_step")}),
        ("Доступ организации — только по зафиксированному согласию", {"fields": (
            "partner_organization", "partner_sharing_approved", "partner_consent_record", "partner_summary", "partner_next_step")}),
        ("Учёт", {"fields": ("public_id", "policy_version", "consented_at", "created_at", "updated_at")}))
    inlines = (CaseMessageInline, CaseEventInline)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        watched = ("status", "coordinator_id", "partner_organization_id", "partner_sharing_approved")
        previous = SupportCase.objects.filter(pk=obj.pk).values(*watched).first() if change else None
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            changes = {field: {"before": previous[field], "after": getattr(obj, field)} for field in watched
                if previous and previous[field] != getattr(obj, field)}
            CaseEvent.objects.create(case=obj, actor=request.user, event_type="staff_updated", detail={"changes": changes})

class StaffMessageForm(forms.ModelForm):
    class Meta:
        model = CaseMessage
        fields = ("case", "audience", "body")

    def clean(self):
        data = super().clean()
        case = data.get("case")
        if case and data.get("audience") == CaseMessage.Audience.PARTNER:
            if not case.partner_organization_id or not case.partner_sharing_approved or not case.partner_organization.is_approved or case.partner_organization.kind in {Organization.Kind.EMPLOYER, Organization.Kind.STAFFING}:
                self.add_error("audience", "Перед сообщением организации нужен её подтверждённый доступ к обращению.")
        return data

@admin.register(CaseMessage)
class CaseMessageAdmin(admin.ModelAdmin):
    form = StaffMessageForm
    list_display = ("case", "author", "audience", "created_at")
    list_filter = ("audience",)
    autocomplete_fields = ("case",)
    fields = ("case", "audience", "body", "author", "partner_organization", "created_at")
    readonly_fields = ("author", "partner_organization", "created_at")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.author = request.user
        if obj.audience == CaseMessage.Audience.PARTNER:
            obj.partner_organization = obj.case.partner_organization
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            SupportCase.objects.filter(pk=obj.case_id).update(updated_at=timezone.now())
            CaseEvent.objects.create(case=obj.case, actor=request.user, event_type="staff_message", detail={"audience": obj.audience})

@admin.register(CaseEvent)
class CaseEventAdmin(admin.ModelAdmin):
    list_display = ("case", "actor", "event_type", "created_at")
    readonly_fields = ("case", "actor", "event_type", "detail", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ImmutableOrganizationAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OrganizationWorkspace)
class OrganizationWorkspaceAdmin(ImmutableOrganizationAdmin):
    list_display = ("organization", "revision", "updated_at")
    readonly_fields = ("organization", "revision", "data", "updated_at")


class OrganizationMessageInline(admin.TabularInline):
    model = OrganizationRequestMessage
    fields = ("author", "body", "is_staff_reply", "created_at")
    readonly_fields = fields
    can_delete = False
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(OrganizationRequest)
class OrganizationRequestAdmin(admin.ModelAdmin):
    list_display = ("reference", "organization", "title", "category", "status", "is_test", "updated_at")
    list_filter = ("status", "category", "is_test")
    search_fields = ("title", "organization__name")
    readonly_fields = ("reference", "public_id", "organization", "created_by", "title", "category", "body",
        "project_id", "is_test", "policy_version", "consented_at", "created_at", "updated_at")
    fields = readonly_fields + ("status",)
    inlines = (OrganizationMessageInline,)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        previous = OrganizationRequest.objects.get(pk=obj.pk).status
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            OrganizationEvent.objects.create(organization=obj.organization, request=obj, actor=request.user,
                event_type="staff_status_changed", detail={"before": previous, "after": obj.status})


class OrganizationReplyForm(forms.ModelForm):
    class Meta:
        model = OrganizationRequestMessage
        fields = ("request", "body")

    def clean_request(self):
        item = self.cleaned_data["request"]
        if not item.organization.is_approved:
            raise forms.ValidationError("Организация не подтверждена; отправка ответа недоступна.")
        if item.status in {OrganizationRequest.Status.CLOSED, OrganizationRequest.Status.RESOLVED}:
            raise forms.ValidationError("Переписка закрыта. При необходимости сначала откройте обращение.")
        return item


@admin.register(OrganizationRequestMessage)
class OrganizationRequestMessageAdmin(admin.ModelAdmin):
    form = OrganizationReplyForm
    list_display = ("request", "author", "is_staff_reply", "created_at")
    fields = ("request", "body", "author", "is_staff_reply", "created_at")
    readonly_fields = ("author", "is_staff_reply", "created_at")
    autocomplete_fields = ("request",)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.author = request.user
        obj.is_staff_reply = True
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            OrganizationRequest.objects.filter(pk=obj.request_id).update(updated_at=timezone.now())
            OrganizationEvent.objects.create(organization=obj.request.organization, request=obj.request, actor=request.user,
                event_type="staff_message", detail={"messageId": obj.pk})


@admin.register(OrganizationEvent)
class OrganizationEventAdmin(ImmutableOrganizationAdmin):
    list_display = ("organization", "request", "actor", "event_type", "created_at")
    readonly_fields = ("organization", "request", "actor", "event_type", "detail", "created_at")
