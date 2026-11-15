import django.db.models.deletion
import portal.organization_models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("portal", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="organization", name="kind",
            field=models.CharField(choices=[("ngo", "Фонд / НКО"), ("employer", "Работодатель"),
                ("staffing", "Кадровое агентство"), ("community", "Диаспора / сообщество"),
                ("donor", "Благотворитель"), ("representation", "Представительство"), ("partner", "Партнёр")],
                default="partner", max_length=16, verbose_name="Тип")),
        migrations.AddField(
            model_name="organizationmembership", name="role",
            field=models.CharField(choices=[("manager", "Администратор организации"),
                ("editor", "Координатор организации"), ("viewer", "Наблюдатель")],
                default="editor", max_length=16, verbose_name="Роль")),
        migrations.CreateModel(
            name="OrganizationWorkspace",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("revision", models.PositiveBigIntegerField(default=0, editable=False)),
                ("data", models.JSONField(default=portal.organization_models.empty_organization_workspace)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("organization", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                    related_name="workspace", to="portal.organization")),
            ],
            options={"verbose_name": "рабочее пространство организации", "verbose_name_plural": "рабочие пространства организаций"}),
        migrations.CreateModel(
            name="OrganizationRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("title", models.CharField(max_length=180, verbose_name="Тема")),
                ("category", models.CharField(choices=[("consultation", "Консультация"), ("adaptation", "Адаптация"),
                    ("prearrival", "Подготовка к приезду"), ("referral", "Маршрутизация помощи"), ("event", "Мероприятие"),
                    ("funding", "Поддержка проекта"), ("information", "Информация"), ("team", "Команда и доступ"),
                    ("other", "Другой вопрос")], max_length=20, verbose_name="Услуга")),
                ("body", models.TextField(max_length=6000, verbose_name="Описание")),
                ("project_id", models.UUIDField(blank=True, editable=False, null=True)),
                ("status", models.CharField(choices=[("new", "Получено"), ("triage", "Первичная проверка"),
                    ("in_progress", "В работе"), ("waiting", "Ждём вашего ответа"), ("resolved", "Вопрос решён"),
                    ("closed", "Закрыто")], db_index=True, default="new", max_length=20, verbose_name="Статус")),
                ("is_test", models.BooleanField(default=False, editable=False, verbose_name="Тестовое обращение")),
                ("policy_version", models.CharField(blank=True, editable=False, max_length=80)),
                ("consented_at", models.DateTimeField(editable=False, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(editable=False, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                    related_name="organization_requests", to="portal.organization", verbose_name="Организация")),
            ],
            options={"ordering": ["-updated_at", "-pk"], "verbose_name": "обращение организации", "verbose_name_plural": "обращения организаций"}),
        migrations.CreateModel(
            name="OrganizationRequestMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.TextField(max_length=4000, verbose_name="Сообщение")),
                ("is_staff_reply", models.BooleanField(default=False, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("author", models.ForeignKey(editable=False, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="messages", to="portal.organizationrequest", verbose_name="Обращение организации")),
            ],
            options={"ordering": ["created_at", "pk"], "verbose_name": "ответ организации", "verbose_name_plural": "ответы организациям"}),
        migrations.CreateModel(
            name="OrganizationEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=40)),
                ("detail", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="workspace_events", to="portal.organization")),
                ("request", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="events", to="portal.organizationrequest")),
            ],
            options={"ordering": ["-created_at", "-pk"], "verbose_name": "событие организации", "verbose_name_plural": "события организаций"}),
    ]
