"""Organization-owned work; never a store of applicant case records."""
import uuid
from django.conf import settings
from django.db import models


def empty_organization_workspace():
    return {"profile": {"city": "", "website": "", "description": "", "languages": []},
            "projects": [], "services": [], "documents": []}


class OrganizationWorkspace(models.Model):
    organization = models.OneToOneField("portal.Organization", on_delete=models.CASCADE, related_name="workspace")
    revision = models.PositiveBigIntegerField(default=0, editable=False)
    data = models.JSONField(default=empty_organization_workspace)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "рабочее пространство организации"
        verbose_name_plural = "рабочие пространства организаций"

    def __str__(self):
        return str(self.organization)


class OrganizationRequest(models.Model):
    class Category(models.TextChoices):
        CONSULTATION = "consultation", "Консультация"
        ADAPTATION = "adaptation", "Адаптация"
        PREARRIVAL = "prearrival", "Подготовка к приезду"
        REFERRAL = "referral", "Маршрутизация помощи"
        EVENT = "event", "Мероприятие"
        FUNDING = "funding", "Поддержка проекта"
        INFORMATION = "information", "Информация"
        TEAM = "team", "Команда и доступ"
        OTHER = "other", "Другой вопрос"

    class Status(models.TextChoices):
        NEW = "new", "Получено"
        TRIAGE = "triage", "Первичная проверка"
        IN_PROGRESS = "in_progress", "В работе"
        WAITING = "waiting", "Ждём вашего ответа"
        RESOLVED = "resolved", "Вопрос решён"
        CLOSED = "closed", "Закрыто"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey("portal.Organization", on_delete=models.PROTECT, related_name="organization_requests", verbose_name="Организация")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, editable=False)
    title = models.CharField("Тема", max_length=180)
    category = models.CharField("Услуга", max_length=20, choices=Category.choices)
    body = models.TextField("Описание", max_length=6000)
    project_id = models.UUIDField(null=True, blank=True, editable=False)
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    is_test = models.BooleanField("Тестовое обращение", default=False, editable=False)
    policy_version = models.CharField(max_length=80, blank=True, editable=False)
    consented_at = models.DateTimeField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-pk"]
        verbose_name = "обращение организации"
        verbose_name_plural = "обращения организаций"

    @property
    def reference(self):
        return f"ORG-{self.pk:06d}" if self.pk else "Новое обращение организации"

    def __str__(self):
        return f"{self.reference} · {self.title}"


class OrganizationRequestMessage(models.Model):
    request = models.ForeignKey(OrganizationRequest, on_delete=models.CASCADE, related_name="messages", verbose_name="Обращение организации")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, editable=False)
    body = models.TextField("Сообщение", max_length=4000)
    is_staff_reply = models.BooleanField(default=False, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "ответ организации"
        verbose_name_plural = "ответы организациям"

    def __str__(self):
        return f"{self.request.reference} · сообщение"


class OrganizationEvent(models.Model):
    organization = models.ForeignKey("portal.Organization", on_delete=models.CASCADE, related_name="workspace_events")
    request = models.ForeignKey(OrganizationRequest, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    event_type = models.CharField(max_length=40)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "событие организации"
        verbose_name_plural = "события организаций"
