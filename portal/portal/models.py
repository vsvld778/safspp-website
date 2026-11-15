import uuid
from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse

LANGUAGES = [("ru", "Русский"), ("ky", "Кыргызча"), ("uz", "O‘zbekcha"), ("tg", "Тоҷикӣ"),
             ("kk", "Қазақша"), ("en", "English"), ("be", "Беларуская"), ("hi", "हिन्दी")]

class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=email.strip().casefold(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True or extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have staff and superuser flags")
        return self._create_user(email, password, **extra_fields)

class User(AbstractUser):
    username = None
    email = models.EmailField("Email", unique=True)
    display_name = models.CharField("Как к вам обращаться", max_length=150)
    preferred_language = models.CharField("Язык общения", max_length=8, choices=LANGUAGES, default="ru")
    email_verified = models.BooleanField("Email подтверждён", default=False, editable=False)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["display_name"]
    objects = UserManager()

    class Meta:
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"
        constraints = [models.UniqueConstraint(Lower("email"), name="portal_email_case_insensitive")]

    def save(self, *args, **kwargs):
        self.email = self.email.strip().casefold()
        super().save(*args, **kwargs)

    def get_full_name(self):
        return self.display_name or self.email

    def get_short_name(self):
        return self.display_name or self.email

    def __str__(self):
        return self.get_full_name()

class Organization(models.Model):
    class Kind(models.TextChoices):
        NGO = "ngo", "Фонд / НКО"
        EMPLOYER = "employer", "Работодатель"
        STAFFING = "staffing", "Кадровое агентство"
        COMMUNITY = "community", "Диаспора / сообщество"
        DONOR = "donor", "Благотворитель"
        REPRESENTATION = "representation", "Представительство"
        PARTNER = "partner", "Партнёр"
    name = models.CharField("Название", max_length=200)
    kind = models.CharField("Тип", max_length=16, choices=Kind.choices, default=Kind.PARTNER)
    is_approved = models.BooleanField("Организация проверена", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "организация"
        verbose_name_plural = "организации"

    def __str__(self):
        return self.name

class OrganizationMembership(models.Model):
    class Role(models.TextChoices):
        MANAGER = "manager", "Администратор организации"
        EDITOR = "editor", "Координатор организации"
        VIEWER = "viewer", "Наблюдатель"
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    is_active = models.BooleanField("Доступ включён", default=True)
    role = models.CharField("Роль", max_length=16, choices=Role.choices, default=Role.EDITOR)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "доступ участника"
        verbose_name_plural = "доступы участников"
        constraints = [models.UniqueConstraint(fields=["organization", "user"], name="portal_unique_membership")]

    def __str__(self):
        return f"{self.organization} — {self.user}"

class SupportCase(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Получено"
        TRIAGE = "triage", "Первичная проверка"
        IN_PROGRESS = "in_progress", "В работе"
        WAITING = "waiting", "Ждём вашего ответа"
        RESOLVED = "resolved", "Вопрос решён"
        CLOSED = "closed", "Закрыто"
    class Category(models.TextChoices):
        DOCUMENTS = "documents", "Документы и пребывание"
        EMPLOYMENT = "employment", "Работа и трудовые права"
        ADAPTATION = "adaptation", "Адаптация и бытовые вопросы"
        PREARRIVAL = "prearrival", "Подготовка к переезду"
        OTHER = "other", "Другой вопрос"
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cases", verbose_name="Заявитель")
    title = models.CharField("Кратко о вопросе", max_length=180)
    category = models.CharField("Тема", max_length=20, choices=Category.choices)
    description = models.TextField("Опишите ситуацию", max_length=6000)
    city = models.CharField("Город / регион", max_length=120, blank=True)
    preferred_language = models.CharField("Язык общения", max_length=8, choices=LANGUAGES, default="ru")
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    next_step = models.TextField("Следующий шаг для заявителя", max_length=2000, blank=True)
    coordinator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="coordinated_cases", limit_choices_to={"is_staff": True}, verbose_name="Координатор")
    partner_organization = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True, verbose_name="Организация партнёра")
    partner_sharing_approved = models.BooleanField("Предоставить организации доступ", default=False)
    partner_consent_record = models.TextField("Основание и зафиксированное согласие на передачу", blank=True,
        help_text="Укажите, кто, когда и на передачу какой организации дал согласие. Без этого доступ запрещён.")
    partner_summary = models.TextField("Описание задачи для организации", blank=True, max_length=3000,
        help_text="Это отдельное описание без приватного обращения и контактных данных заявителя.")
    partner_next_step = models.TextField("Следующий шаг для организации", blank=True, max_length=2000)
    policy_version = models.CharField(max_length=80, blank=True, editable=False)
    consented_at = models.DateTimeField(null=True, editable=False)
    is_test = models.BooleanField("Тестовое обращение", default=False, editable=False)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "обращение"
        verbose_name_plural = "обращения"

    @property
    def reference(self):
        return f"MP-{self.pk:06d}" if self.pk else "Новое обращение"

    def get_absolute_url(self):
        return reverse("case_detail", kwargs={"public_id": self.public_id})

    def clean(self):
        previous = SupportCase.objects.filter(pk=self.pk).values("partner_organization_id").first() if self.pk else None
        if previous and previous["partner_organization_id"] and previous["partner_organization_id"] != self.partner_organization_id and self.partner_sharing_approved:
            raise ValidationError({"partner_sharing_approved": "При смене организации сначала сохраните обращение с отключённым доступом. Затем укажите новое согласие и новое описание задачи."})
        if self.partner_sharing_approved:
            if not self.partner_organization_id or not self.partner_organization.is_approved:
                raise ValidationError({"partner_organization": "Выберите проверенную организацию."})
            if self.partner_organization.kind in {Organization.Kind.EMPLOYER, Organization.Kind.STAFFING}:
                raise ValidationError({"partner_organization": "Работодателям и кадровым агентствам доступ к личным обращениям не предоставляется."})
            if not self.partner_consent_record.strip():
                raise ValidationError({"partner_consent_record": "Нужно зафиксированное согласие на передачу."})
            if not self.partner_summary.strip():
                raise ValidationError({"partner_summary": "Укажите описание задачи для организации."})

    def save(self, *args, **kwargs):
        previous = SupportCase.objects.filter(pk=self.pk).values("partner_organization_id").first() if self.pk else None
        if previous and previous["partner_organization_id"] and previous["partner_organization_id"] != self.partner_organization_id:
            self.partner_sharing_approved = False
            self.partner_consent_record = ""
            self.partner_summary = ""
            self.partner_next_step = ""
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"partner_sharing_approved", "partner_consent_record", "partner_summary", "partner_next_step"}
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference} · {self.title}"

class CaseMessage(models.Model):
    class Audience(models.TextChoices):
        APPLICANT = "applicant", "Заявитель и координатор"
        PARTNER = "partner", "Организация, заявитель и координатор"
        INTERNAL = "internal", "Только сотрудники"
    case = models.ForeignKey(SupportCase, on_delete=models.CASCADE, related_name="messages", verbose_name="Обращение")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="Автор")
    body = models.TextField("Сообщение", max_length=4000)
    audience = models.CharField("Видимость", max_length=16, choices=Audience.choices, default=Audience.APPLICANT)
    partner_organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.PROTECT,
        editable=False, help_text="Организация на момент отправки. Старый диалог не передаётся другой организации.")
    created_at = models.DateTimeField("Отправлено", auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "сообщение"
        verbose_name_plural = "сообщения"

    @property
    def author_display(self):
        if self.author.is_staff:
            return "Координатор фонда"
        if self.audience == self.Audience.PARTNER:
            return "Представитель организации"
        return self.author.display_name or "Заявитель"

    def __str__(self):
        return f"{self.case.reference} · {self.get_audience_display()}"

class CaseEvent(models.Model):
    case = models.ForeignKey(SupportCase, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    event_type = models.CharField(max_length=40)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "событие аудита"
        verbose_name_plural = "события аудита"

class RateLimitBucket(models.Model):
    key = models.CharField(max_length=64, unique=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)

# Keep the organization workspace separate from applicants' private case records.
from .organization_models import (OrganizationWorkspace, OrganizationRequest, OrganizationRequestMessage, OrganizationEvent)  # noqa: E402,F401
