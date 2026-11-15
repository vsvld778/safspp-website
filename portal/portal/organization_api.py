"""Same-origin session APIs. Scope is resolved from membership on every request."""
import json
import uuid
from datetime import date
from functools import wraps
from urllib.parse import urlsplit
from django.conf import settings
from django.core.exceptions import RequestDataTooBig, ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.urls import reverse
from django.utils import timezone
from .access import partner_cases
from .models import LANGUAGES, OrganizationMembership
from .organization_models import (OrganizationWorkspace, OrganizationRequest,
    OrganizationRequestMessage, OrganizationEvent, empty_organization_workspace)
from .ratelimit import allow_request

MAX_BYTES = 96 * 1024
WRITE_ROLES = {OrganizationMembership.Role.MANAGER, OrganizationMembership.Role.EDITOR}


class APIError(Exception):
    def __init__(self, error, message, status=400):
        self.error, self.message, self.status = error, message, status


def fail(message, error="invalid_data", status=400):
    raise APIError(error, message, status)


def api(methods):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            try:
                if not request.user.is_authenticated or not request.user.is_active:
                    fail("Войдите в кабинет организации.", "authentication_required", 401)
                if request.method not in methods:
                    fail("Этот метод не поддерживается.", "method_not_allowed", 405)
                # Locks serialize workspace creation and prevent a membership revocation
                # from racing a write. No superuser/staff bypass on organization APIs.
                with transaction.atomic():
                    memberships = OrganizationMembership.objects.filter(user=request.user,
                        user__is_active=True, is_active=True, organization__is_approved=True).select_related("organization").order_by("organization_id")
                    if request.method != "GET":
                        memberships = memberships.select_for_update()
                    selected = request.GET.get("organization")
                    if selected is not None:
                        if not selected.isdecimal() or len(selected) > 18:
                            fail("Организация недоступна.", "organization_forbidden", 403)
                        membership = memberships.filter(organization_id=int(selected)).first()
                    else:
                        membership = memberships.first()
                    if membership is None:
                        fail("Доступ к подтверждённой организации не предоставлен.", "organization_forbidden", 403)
                    request.organization_membership = membership
                    if request.method != "GET":
                        if membership.role not in WRITE_ROLES:
                            fail("Для этой роли доступно только чтение.", "read_only", 403)
                        if settings.PORTAL_INTAKE_MODE == "disabled":
                            fail("Приём и изменение данных пока приостановлены.", "intake_disabled", 403)
                        if not allow_request("organization-write", str(request.user.pk), 60, 600):
                            fail("Слишком много изменений. Повторите позже.", "rate_limited", 429)
                    try:
                        return view(request, *args, **kwargs)
                    except APIError as exc:
                        # Validation failures still consume the persisted rate bucket.
                        return JsonResponse({"error": exc.error, "message": exc.message}, status=exc.status)
            except APIError as exc:
                return JsonResponse({"error": exc.error, "message": exc.message}, status=exc.status)
        return wrapped
    return decorator


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def payload(request, fields, required):
    if request.content_type != "application/json":
        fail("Передайте JSON.", "unsupported_media_type", 415)
    try:
        if int(request.META.get("CONTENT_LENGTH") or 0) > MAX_BYTES:
            fail("Данные превышают 96 КиБ.", "payload_too_large", 413)
        raw = request.body
        if len(raw) > MAX_BYTES:
            fail("Данные превышают 96 КиБ.", "payload_too_large", 413)
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Invalid number")))
    except RequestDataTooBig:
        fail("Данные превышают допустимый размер.", "payload_too_large", 413)
    except (ValueError, UnicodeError, RecursionError):
        fail("Некорректный JSON.")
    object_keys(data, fields, required)
    if settings.PORTAL_INTAKE_MODE == "test" and data.get("testDataOnly") is not True:
        fail("Подтвердите, что используете только вымышленные тестовые данные.", "test_confirmation_required")
    for flag in ("testDataOnly", "privacyConsent"):
        if flag in data and type(data[flag]) is not bool:
            fail("Подтверждение должно быть логическим значением.")
    return data


def object_keys(value, allowed, required=None):
    if type(value) is not dict or set(value) - set(allowed) or set(required or ()) - set(value):
        fail("Неизвестные или отсутствующие поля.")


def text_value(value, limit, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        fail("Проверьте обязательные поля и длину текста.")
    try:
        value.encode("utf-8")
    except UnicodeError:
        fail("Недопустимые символы в тексте.")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
        fail("Недопустимые символы в тексте.")
    return value


def identifier(value, optional=False):
    if optional and value in ("", None):
        return None
    if not isinstance(value, str):
        fail("Некорректный идентификатор.")
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        fail("Некорректный идентификатор.")
    if str(parsed) != value:
        fail("Используйте UUID в стандартном формате.")
    return parsed


def https_url(value, required=False):
    text_value(value, 500, required)
    if not value:
        return value
    try:
        URLValidator(schemes=["https"])(value)
        parts = urlsplit(value)
        if parts.username or parts.password:
            fail("Ссылка не должна содержать учётные данные.")
    except (ValidationError, ValueError):
        fail("Укажите полную HTTPS-ссылку.")
    return value


def validate_workspace(data):
    object_keys(data, {"profile", "projects", "services", "documents"}, {"profile", "projects", "services", "documents"})
    profile = data["profile"]
    object_keys(profile, {"city", "website", "description", "languages"}, {"city", "website", "description", "languages"})
    text_value(profile["city"], 120)
    https_url(profile["website"])
    text_value(profile["description"], 3000)
    languages = profile["languages"]
    if type(languages) is not list or len(languages) > 8 or any(not isinstance(x, str) or x not in dict(LANGUAGES) for x in languages) or len(set(languages)) != len(languages):
        fail("Выберите языки из доступного списка.")
    item_ids = {}
    definitions = {
        "projects": {"id", "title", "description", "status", "deadline"},
        "services": {"id", "title", "description", "category", "available"},
        "documents": {"id", "title", "category", "url", "note", "projectId"},
    }
    for collection, fields in definitions.items():
        items = data[collection]
        if type(items) is not list or len(items) > 100:
            fail("В одном разделе допускается не более 100 записей.")
        ids = set()
        for item in items:
            object_keys(item, fields, fields)
            identifier(item["id"])
            if item["id"] in ids:
                fail("Идентификаторы записей не должны повторяться.")
            ids.add(item["id"])
            text_value(item["title"], 180, True)
            if collection == "projects":
                text_value(item["description"], 3000)
                if item["status"] not in ("planned", "active", "paused", "completed"):
                    fail("Некорректный статус проекта.")
                text_value(item["deadline"], 10)
                if item["deadline"]:
                    try:
                        if date.fromisoformat(item["deadline"]).isoformat() != item["deadline"]:
                            raise ValueError
                    except ValueError:
                        fail("Укажите дату в формате ГГГГ-ММ-ДД.")
            elif collection == "services":
                text_value(item["description"], 2000)
                if item["category"] not in OrganizationRequest.Category.values or type(item["available"]) is not bool:
                    fail("Проверьте категорию и доступность услуги.")
            else:
                if item["category"] not in ("agreement", "report", "template", "other"):
                    fail("Некорректная категория документа.")
                https_url(item["url"], True)
                text_value(item["note"], 2000)
                identifier(item["projectId"], optional=True)
        item_ids[collection] = ids
    for document in data["documents"]:
        if document["projectId"] and document["projectId"] not in item_ids["projects"]:
            fail("Документ может быть связан только с проектом этой организации.")
    return data


def org_presentation(org):
    return {"id": org.pk, "name": org.name, "kind": org.kind}


@api({"GET"})
def session(request):
    member = request.organization_membership
    organization = member.organization
    can_write = member.role in WRITE_ROLES and settings.PORTAL_INTAKE_MODE != "disabled"
    cases = [{"id": str(case.public_id), "reference": case.reference, "status": case.status,
        "statusLabel": case.get_status_display(), "summary": case.partner_summary,
        "nextStep": case.partner_next_step, "updatedAt": case.updated_at.isoformat(), "isTest": case.is_test,
        "url": reverse("partner_case_detail", kwargs={"public_id": case.public_id})}
        for case in partner_cases(request.user).filter(partner_organization=organization)[:100]]
    return JsonResponse({"user": {"name": request.user.display_name or "Участник"},
        "organizations": [org_presentation(item.organization) for item in OrganizationMembership.objects.filter(
            user=request.user, is_active=True, organization__is_approved=True).select_related("organization").order_by("organization_id")],
        "organization": org_presentation(organization), "membership": {"role": member.role},
        "members": [{"name": item.user.display_name or "Участник", "role": item.role}
            for item in OrganizationMembership.objects.filter(organization=organization, is_active=True,
                user__is_active=True).select_related("user").order_by("pk")[:200]],
        "csrfToken": get_token(request), "intakeMode": settings.PORTAL_INTAKE_MODE,
        "policyUrl": settings.PORTAL_POLICY_URL, "policyVersion": settings.PORTAL_POLICY_VERSION,
        "operatorName": settings.PORTAL_OPERATOR_NAME,
        "capabilities": {"canWrite": can_write, "canManage": can_write and member.role == OrganizationMembership.Role.MANAGER},
        "cases": cases})


def workspace_presentation(workspace):
    return {"revision": workspace.revision if workspace else 0,
        "data": workspace.data if workspace else empty_organization_workspace(),
        "updatedAt": workspace.updated_at.isoformat() if workspace else None}


@api({"GET", "PUT"})
def workspace(request):
    member = request.organization_membership
    record = OrganizationWorkspace.objects.filter(organization=member.organization).first()
    if request.method == "GET":
        return JsonResponse(workspace_presentation(record))
    data = payload(request, {"revision", "data", "testDataOnly"}, {"revision", "data"})
    if type(data["revision"]) is not int or not 0 <= data["revision"] < 2**63 - 1:
        fail("Некорректная версия рабочего пространства.")
    current = workspace_presentation(record)
    if data["revision"] != current["revision"]:
        fail("Данные уже изменены. Загрузите новую версию и повторите изменения.", "revision_conflict", 409)
    clean_data = validate_workspace(data["data"])
    if member.role != OrganizationMembership.Role.MANAGER and clean_data["profile"] != current["data"]["profile"]:
        fail("Профиль может изменять только администратор организации.", "profile_forbidden", 403)
    if record is None:
        record = OrganizationWorkspace(organization=member.organization)
    record.data = clean_data
    record.revision += 1
    record.save()
    OrganizationEvent.objects.create(organization=member.organization, actor=request.user,
        event_type="workspace_updated", detail={"revision": record.revision,
            "counts": {key: len(clean_data[key]) for key in ("projects", "services", "documents")}})
    return JsonResponse(workspace_presentation(record))


def request_presentation(item, detail=False):
    result = {"id": str(item.public_id), "reference": item.reference, "title": item.title,
        "category": item.category, "status": item.status, "statusLabel": item.get_status_display(),
        "projectId": str(item.project_id) if item.project_id else "", "isTest": item.is_test,
        "createdAt": item.created_at.isoformat(), "updatedAt": item.updated_at.isoformat()}
    if detail:
        result["body"] = item.body
    return result


def request_detail(item, user):
    return {"request": request_presentation(item, detail=True), "messages": [
        {"id": message.pk, "body": message.body,
         "authorName": "Координатор фонда" if message.is_staff_reply else message.author.display_name or "Участник организации",
         "isOwn": message.author_id == user.pk, "isStaff": message.is_staff_reply,
         "createdAt": message.created_at.isoformat()}
        for message in item.messages.select_related("author").all()]}


@api({"GET", "POST"})
def requests(request):
    organization = request.organization_membership.organization
    if request.method == "GET":
        return JsonResponse({"requests": [request_presentation(item) for item in OrganizationRequest.objects.filter(organization=organization)[:200]]})
    data = payload(request, {"title", "category", "body", "projectId", "testDataOnly", "privacyConsent"}, {"title", "category", "body"})
    text_value(data["title"], 180, True)
    text_value(data["body"], 6000, True)
    if data["category"] not in OrganizationRequest.Category.values:
        fail("Выберите услугу из списка.")
    project_id = identifier(data.get("projectId"), optional=True)
    if project_id:
        record = OrganizationWorkspace.objects.filter(organization=organization).first()
        if not record or str(project_id) not in {item["id"] for item in record.data["projects"]}:
            fail("Проект этой организации не найден.", "project_not_found", 404)
    if settings.PORTAL_INTAKE_MODE == "live" and data.get("privacyConsent") is not True:
        fail("Необходимо согласие с условиями обработки обращения.", "consent_required")
    if not allow_request("organization-request-create", str(request.user.pk), 8, 3600):
        fail("Слишком много обращений. Повторите позже.", "rate_limited", 429)
    item = OrganizationRequest.objects.create(organization=organization, created_by=request.user,
        title=data["title"].strip(), category=data["category"], body=data["body"].strip(), project_id=project_id,
        is_test=settings.PORTAL_INTAKE_MODE == "test", consented_at=timezone.now(),
        policy_version="synthetic-test" if settings.PORTAL_INTAKE_MODE == "test" else settings.PORTAL_POLICY_VERSION)
    OrganizationEvent.objects.create(organization=organization, request=item, actor=request.user,
        event_type="request_created", detail={"test": item.is_test})
    return JsonResponse(request_detail(item, request.user), status=201)


@api({"GET", "POST"})
def request_item(request, public_id):
    organization = request.organization_membership.organization
    items = OrganizationRequest.objects.filter(organization=organization, public_id=public_id)
    if request.method == "POST":
        items = items.select_for_update()
    item = items.first()
    if item is None:
        fail("Обращение не найдено.", "not_found", 404)
    if request.method == "GET":
        return JsonResponse(request_detail(item, request.user))
    data = payload(request, {"body", "testDataOnly"}, {"body"})
    text_value(data["body"], 4000, True)
    if item.status in {OrganizationRequest.Status.CLOSED, OrganizationRequest.Status.RESOLVED}:
        fail("Переписка завершённого обращения закрыта.", "request_closed", 409)
    if not allow_request("organization-message", str(request.user.pk), 30, 600):
        fail("Слишком много сообщений. Повторите позже.", "rate_limited", 429)
    message = OrganizationRequestMessage.objects.create(request=item, author=request.user, body=data["body"].strip())
    item.save(update_fields=["updated_at"])
    OrganizationEvent.objects.create(organization=organization, request=item, actor=request.user,
        event_type="message_added", detail={"messageId": message.pk})
    return JsonResponse(request_detail(item, request.user), status=201)
