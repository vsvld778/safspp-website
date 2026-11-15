import django.db.models.deletion
import django.db.models.functions.text
import django.utils.timezone
import portal.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("auth", "0012_alter_user_first_name_max_length")]

    operations = [
        migrations.CreateModel(
            name="Organization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, verbose_name="Название")),
                ("kind", models.CharField(choices=[("ngo", "Фонд / НКО"), ("employer", "Работодатель"), ("partner", "Партнёр")], default="partner", max_length=16, verbose_name="Тип")),
                ("is_approved", models.BooleanField(default=False, verbose_name="Организация проверена")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name": "организация", "verbose_name_plural": "организации"},
        ),
        migrations.CreateModel(
            name="RateLimitBucket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=64, unique=True)),
                ("count", models.PositiveIntegerField(default=0)),
                ("expires_at", models.DateTimeField(db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(default=False, help_text="Designates that this user has all permissions without explicitly assigning them.", verbose_name="superuser status")),
                ("first_name", models.CharField(blank=True, max_length=150, verbose_name="first name")),
                ("last_name", models.CharField(blank=True, max_length=150, verbose_name="last name")),
                ("is_staff", models.BooleanField(default=False, help_text="Designates whether the user can log into this admin site.", verbose_name="staff status")),
                ("is_active", models.BooleanField(default=True, help_text="Designates whether this user should be treated as active. Unselect this instead of deleting accounts.", verbose_name="active")),
                ("date_joined", models.DateTimeField(default=django.utils.timezone.now, verbose_name="date joined")),
                ("email", models.EmailField(max_length=254, unique=True, verbose_name="Email")),
                ("display_name", models.CharField(max_length=150, verbose_name="Как к вам обращаться")),
                ("preferred_language", models.CharField(choices=[("ru", "Русский"), ("ky", "Кыргызча"), ("uz", "O‘zbekcha"), ("tg", "Тоҷикӣ"), ("kk", "Қазақша"), ("en", "English"), ("be", "Беларуская"), ("hi", "हिन्दी")], default="ru", max_length=8, verbose_name="Язык общения")),
                ("email_verified", models.BooleanField(default=False, editable=False, verbose_name="Email подтверждён")),
                ("groups", models.ManyToManyField(blank=True, help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.", related_name="user_set", related_query_name="user", to="auth.group", verbose_name="groups")),
                ("user_permissions", models.ManyToManyField(blank=True, help_text="Specific permissions for this user.", related_name="user_set", related_query_name="user", to="auth.permission", verbose_name="user permissions")),
            ],
            options={"verbose_name": "пользователь", "verbose_name_plural": "пользователи"},
            managers=[("objects", portal.models.UserManager())],
        ),
        migrations.CreateModel(
            name="OrganizationMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(default=True, verbose_name="Доступ включён")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="portal.organization")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "доступ участника", "verbose_name_plural": "доступы участников"},
        ),
        migrations.CreateModel(
            name="SupportCase",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("title", models.CharField(max_length=180, verbose_name="Кратко о вопросе")),
                ("category", models.CharField(choices=[("documents", "Документы и пребывание"), ("employment", "Работа и трудовые права"), ("adaptation", "Адаптация и бытовые вопросы"), ("prearrival", "Подготовка к переезду"), ("other", "Другой вопрос")], max_length=20, verbose_name="Тема")),
                ("description", models.TextField(max_length=6000, verbose_name="Опишите ситуацию")),
                ("city", models.CharField(blank=True, max_length=120, verbose_name="Город / регион")),
                ("preferred_language", models.CharField(choices=[("ru", "Русский"), ("ky", "Кыргызча"), ("uz", "O‘zbekcha"), ("tg", "Тоҷикӣ"), ("kk", "Қазақша"), ("en", "English"), ("be", "Беларуская"), ("hi", "हिन्दी")], default="ru", max_length=8, verbose_name="Язык общения")),
                ("status", models.CharField(choices=[("new", "Получено"), ("triage", "Первичная проверка"), ("in_progress", "В работе"), ("waiting", "Ждём вашего ответа"), ("resolved", "Вопрос решён"), ("closed", "Закрыто")], db_index=True, default="new", max_length=20, verbose_name="Статус")),
                ("next_step", models.TextField(blank=True, max_length=2000, verbose_name="Следующий шаг для заявителя")),
                ("partner_sharing_approved", models.BooleanField(default=False, verbose_name="Предоставить организации доступ")),
                ("partner_consent_record", models.TextField(blank=True, help_text="Укажите, кто, когда и на передачу какой организации дал согласие. Без этого доступ запрещён.", verbose_name="Основание и зафиксированное согласие на передачу")),
                ("partner_summary", models.TextField(blank=True, help_text="Это отдельное описание без приватного обращения и контактных данных заявителя.", max_length=3000, verbose_name="Описание задачи для организации")),
                ("partner_next_step", models.TextField(blank=True, max_length=2000, verbose_name="Следующий шаг для организации")),
                ("policy_version", models.CharField(blank=True, editable=False, max_length=80)),
                ("consented_at", models.DateTimeField(editable=False, null=True)),
                ("is_test", models.BooleanField(default=False, editable=False, verbose_name="Тестовое обращение")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                ("coordinator", models.ForeignKey(blank=True, limit_choices_to={"is_staff": True}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="coordinated_cases", to=settings.AUTH_USER_MODEL, verbose_name="Координатор")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cases", to=settings.AUTH_USER_MODEL, verbose_name="Заявитель")),
                ("partner_organization", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="portal.organization", verbose_name="Организация партнёра")),
            ],
            options={"verbose_name": "обращение", "verbose_name_plural": "обращения", "ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="CaseMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.TextField(max_length=4000, verbose_name="Сообщение")),
                ("audience", models.CharField(choices=[("applicant", "Заявитель и координатор"), ("partner", "Организация, заявитель и координатор"), ("internal", "Только сотрудники")], default="applicant", max_length=16, verbose_name="Видимость")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Отправлено")),
                ("author", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL, verbose_name="Автор")),
                ("case", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="portal.supportcase", verbose_name="Обращение")),
                ("partner_organization", models.ForeignKey(blank=True, editable=False, help_text="Организация на момент отправки. Старый диалог не передаётся другой организации.", null=True, on_delete=django.db.models.deletion.PROTECT, to="portal.organization")),
            ],
            options={"verbose_name": "сообщение", "verbose_name_plural": "сообщения", "ordering": ["created_at", "pk"]},
        ),
        migrations.CreateModel(
            name="CaseEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=40)),
                ("detail", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("case", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="portal.supportcase")),
            ],
            options={"verbose_name": "событие аудита", "verbose_name_plural": "события аудита", "ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(model_name="user", constraint=models.UniqueConstraint(django.db.models.functions.text.Lower("email"), name="portal_email_case_insensitive")),
        migrations.AddConstraint(model_name="organizationmembership", constraint=models.UniqueConstraint(fields=("organization", "user"), name="portal_unique_membership")),
    ]
