from django.contrib import admin
from django import forms
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.db import transaction
from django.utils import timezone
from .models import CaseEvent, CaseMessage, Organization, OrganizationMembership, SupportCase, User

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

@admin.register(OrganizationMembership)
class MembershipAdmin(SuperuserManagedAdmin):
    list_display = ("organization", "user", "is_active")
    list_filter = ("is_active", "organization")
    autocomplete_fields = ("organization", "user")

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
            if not case.partner_organization_id or not case.partner_sharing_approved or not case.partner_organization.is_approved:
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
