import hashlib
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from .models import CaseEvent, CaseMessage, Organization, OrganizationMembership, SupportCase

@override_settings(PORTAL_INTAKE_MODE="test", REGISTRATION_MODE="closed")
class PortalAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice@example.test", "Example-test-password-984!", display_name="Алия")
        cls.bob = User.objects.create_user("bob@example.test", "Example-test-password-984!", display_name="Боб")
        cls.partner = User.objects.create_user("partner@example.test", "Example-test-password-984!", display_name="Партнёр")
        cls.other_partner = User.objects.create_user("other@example.test", "Example-test-password-984!", display_name="Другой партнёр")
        cls.staff = User.objects.create_user("staff@example.test", "Example-test-password-984!", display_name="Координатор", is_staff=True)
        cls.org = Organization.objects.create(name="Тестовая организация", is_approved=True)
        cls.other_org = Organization.objects.create(name="Другая организация", is_approved=True)
        OrganizationMembership.objects.create(user=cls.partner, organization=cls.org)
        OrganizationMembership.objects.create(user=cls.other_partner, organization=cls.other_org)
        cls.case = SupportCase.objects.create(owner=cls.alice, title="Секретное название", category="employment",
            description="Личное описание ситуации", city="Тестовый город", is_test=True,
            partner_organization=cls.org, partner_sharing_approved=True, partner_consent_record="Синтетическое согласие",
            partner_summary="Общая задача для партнёра", partner_next_step="Ответить координатору")
        cls.private = CaseMessage.objects.create(case=cls.case, author=cls.alice, body="Приватное сообщение заявителя")
        cls.internal = CaseMessage.objects.create(case=cls.case, author=cls.staff, body="Внутренняя заметка", audience="internal")
        cls.shared = CaseMessage.objects.create(case=cls.case, author=cls.staff, body="Сообщение для организации", audience="partner", partner_organization=cls.org)

    def login_as(self, user):
        self.client.force_login(user, backend="portal.auth.ThrottledEmailBackend")

    def test_anonymous_cannot_read_or_post_cases(self):
        for url in [reverse("dashboard"), self.case.get_absolute_url(), reverse("case_create"),
                    reverse("partner_case_detail", args=[self.case.public_id])]:
            self.assertEqual(self.client.get(url).status_code, 302)
            self.assertEqual(self.client.post(url, {"body": "unauthorized"}).status_code, 302)
        self.assertEqual(CaseMessage.objects.count(), 3)

    def test_owner_reads_only_external_thread(self):
        self.login_as(self.alice)
        response = self.client.get(self.case.get_absolute_url())
        self.assertContains(response, "Личное описание ситуации")
        self.assertContains(response, "Приватное сообщение заявителя")
        self.assertContains(response, "Сообщение для организации")
        self.assertNotContains(response, "Внутренняя заметка")

    def test_other_applicant_cannot_read_or_post_case(self):
        self.login_as(self.bob)
        self.assertEqual(self.client.get(self.case.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.post(self.case.get_absolute_url(), {"body": "injected"}).status_code, 404)
        self.assertEqual(CaseMessage.objects.count(), 3)
        self.assertNotContains(self.client.get(reverse("dashboard")), "Секретное название")

    def test_staff_cabinet_does_not_bypass_owner_scope(self):
        self.login_as(self.staff)
        self.assertEqual(self.client.get(self.case.get_absolute_url()).status_code, 404)

    def test_partner_only_sees_explicit_shared_projection(self):
        self.login_as(self.partner)
        for url in [reverse("partner_dashboard"), reverse("partner_case_detail", args=[self.case.public_id])]:
            response = self.client.get(url)
            self.assertContains(response, "Общая задача для партнёра")
            for private in ["Личное описание ситуации", "Секретное название", "alice@example.test", "Приватное сообщение заявителя", "Внутренняя заметка"]:
                self.assertNotContains(response, private)
        self.assertContains(self.client.get(reverse("partner_case_detail", args=[self.case.public_id])), "Сообщение для организации")

    def test_unassigned_organization_cannot_read_or_post(self):
        self.login_as(self.other_partner)
        url = reverse("partner_case_detail", args=[self.case.public_id])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"body": "injected"}).status_code, 404)
        self.assertNotContains(self.client.get(reverse("partner_dashboard")), "Общая задача для партнёра")

    def test_partner_cannot_use_applicant_endpoint(self):
        self.login_as(self.partner)
        self.assertEqual(self.client.get(self.case.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.post(self.case.get_absolute_url(), {"body": "injected"}).status_code, 404)

    def test_revoked_membership_loses_access_immediately(self):
        self.login_as(self.partner)
        OrganizationMembership.objects.filter(user=self.partner).update(is_active=False)
        self.assertEqual(self.client.get(reverse("partner_case_detail", args=[self.case.public_id])).status_code, 404)

    def test_unapproved_organization_loses_access_immediately(self):
        self.login_as(self.partner)
        self.org.is_approved = False
        self.org.save()
        self.assertEqual(self.client.get(reverse("partner_case_detail", args=[self.case.public_id])).status_code, 404)

    def test_sharing_disabled_loses_access(self):
        self.login_as(self.partner)
        self.case.partner_sharing_approved = False
        self.case.save()
        self.assertEqual(self.client.get(reverse("partner_case_detail", args=[self.case.public_id])).status_code, 404)

    def test_partner_reassignment_does_not_expose_old_partner_thread(self):
        self.case.partner_organization = self.other_org
        self.case.partner_sharing_approved = False
        self.case.save()
        self.case.partner_consent_record = "Новое синтетическое согласие для другой организации"
        self.case.partner_summary = "Новая совместная задача"
        self.case.partner_sharing_approved = True
        self.case.save()
        self.login_as(self.other_partner)
        response = self.client.get(reverse("partner_case_detail", args=[self.case.public_id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Сообщение для организации")

    def test_partner_reassignment_requires_new_consent_and_clears_old_projection(self):
        self.case.partner_organization = self.other_org
        with self.assertRaises(ValidationError):
            self.case.full_clean()
        self.case.save()
        self.case.refresh_from_db()
        self.assertFalse(self.case.partner_sharing_approved)
        self.assertEqual(self.case.partner_consent_record, "")
        self.assertEqual(self.case.partner_summary, "")
        self.assertEqual(self.case.partner_next_step, "")
        self.login_as(self.other_partner)
        self.assertEqual(self.client.get(reverse("partner_case_detail", args=[self.case.public_id])).status_code, 404)

    def test_case_creation_sets_owner_server_side_and_test_marker(self):
        self.login_as(self.alice)
        response = self.client.post(reverse("case_create"), {"title": "Проверка", "category": "other", "description": "Вымышленная ситуация",
            "city": "Тест", "preferred_language": "ru", "test_data_only": "on", "owner": self.bob.pk,
            "status": "resolved", "partner_sharing_approved": "on"})
        self.assertEqual(response.status_code, 302)
        created = SupportCase.objects.get(title="Проверка")
        self.assertEqual(created.owner, self.alice)
        self.assertEqual(created.status, "new")
        self.assertFalse(created.partner_sharing_approved)
        self.assertTrue(created.is_test)
        self.assertEqual(created.policy_version, "synthetic-test")
        self.assertEqual(created.events.get().event_type, "created")

    def test_test_case_requires_synthetic_confirmation(self):
        self.login_as(self.alice)
        response = self.client.post(reverse("case_create"), {"title": "Нет согласия", "category": "other", "description": "Тест", "preferred_language": "ru"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SupportCase.objects.filter(title="Нет согласия").exists())

    @override_settings(PORTAL_INTAKE_MODE="disabled")
    def test_disabled_intake_rejects_creation(self):
        self.login_as(self.alice)
        self.assertRedirects(self.client.post(reverse("case_create"), {}), reverse("dashboard"))

    def test_message_author_and_audience_are_server_owned(self):
        self.login_as(self.alice)
        self.client.post(self.case.get_absolute_url(), {"body": "Новый ответ", "author": self.staff.pk, "audience": "internal", "case": 999})
        message = CaseMessage.objects.get(body="Новый ответ")
        self.assertEqual(message.author, self.alice)
        self.assertEqual(message.case, self.case)
        self.assertEqual(message.audience, "applicant")

    def test_partner_message_scoped_to_current_organization(self):
        self.login_as(self.partner)
        self.client.post(reverse("partner_case_detail", args=[self.case.public_id]), {"body": "Ответ партнёра", "audience": "applicant"})
        message = CaseMessage.objects.get(body="Ответ партнёра")
        self.assertEqual(message.audience, "partner")
        self.assertEqual(message.partner_organization, self.org)

    def test_closed_case_rejects_new_messages(self):
        self.case.status = "closed"
        self.case.save()
        self.login_as(self.alice)
        self.client.post(self.case.get_absolute_url(), {"body": "После закрытия"})
        self.assertFalse(CaseMessage.objects.filter(body="После закрытия").exists())

    def test_shared_case_requires_consent_record(self):
        self.case.partner_consent_record = ""
        with self.assertRaises(ValidationError):
            self.case.full_clean()

    def test_csrf_required_for_authenticated_post(self):
        secure_client = Client(enforce_csrf_checks=True)
        secure_client.force_login(self.alice)
        self.assertEqual(secure_client.post(self.case.get_absolute_url(), {"body": "CSRF"}).status_code, 403)
        self.assertFalse(CaseMessage.objects.filter(body="CSRF").exists())

    def test_logout_requires_post(self):
        self.login_as(self.alice)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertEqual(self.client.post(reverse("logout")).status_code, 302)

    def test_private_responses_are_not_cacheable(self):
        self.login_as(self.alice)
        response = self.client.get(self.case.get_absolute_url())
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("noindex", response["X-Robots-Tag"])
        self.assertIn("frame-ancestors 'none'", response["Content-Security-Policy"])

    def test_html_message_is_escaped(self):
        self.login_as(self.alice)
        CaseMessage.objects.create(case=self.case, author=self.alice, body="<script>alert(1)</script>")
        response = self.client.get(self.case.get_absolute_url())
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_health_endpoint_does_not_expose_system_details(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.json(), {"status": "ok"})

    def test_pending_partner_page_exposes_no_case_data(self):
        self.login_as(self.bob)
        response = self.client.get(reverse("partner_dashboard"))
        self.assertContains(response, "ещё не подключён")
        self.assertNotContains(response, "Общая задача для партнёра")

@override_settings(PORTAL_INTAKE_MODE="test", REGISTRATION_MODE="invite",
    REGISTRATION_INVITE_SHA256=hashlib.sha256(b"synthetic-test-invitation").hexdigest())
class AuthenticationTests(TestCase):
    def signup_data(self, **extra):
        data = {"email": "New@example.test", "display_name": "Тест", "preferred_language": "ru",
            "password1": "Synthetic-long-password-472!", "password2": "Synthetic-long-password-472!",
            "invite_code": "synthetic-test-invitation"}
        data.update(extra)
        return data

    def test_registration_requires_invitation_and_does_not_verify_email(self):
        response = self.client.post(reverse("signup"), self.signup_data(invite_code="wrong"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.exists())
        response = self.client.post(reverse("signup"), self.signup_data(is_staff="on", email_verified="on"))
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(email="new@example.test")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.email_verified)
        self.assertTrue(user.check_password("Synthetic-long-password-472!"))
        self.assertNotEqual(user.password, "Synthetic-long-password-472!")

    @override_settings(REGISTRATION_MODE="closed")
    def test_closed_registration_blocks_post(self):
        self.assertEqual(self.client.post(reverse("signup"), self.signup_data()).status_code, 403)
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_login_case_insensitive_and_external_next_rejected(self):
        get_user_model().objects.create_user("tester@example.test", "Synthetic-long-password-472!", display_name="Тест")
        response = self.client.post(reverse("login"), {"username": "TESTER@EXAMPLE.TEST", "password": "Synthetic-long-password-472!", "next": "https://evil.example/"})
        self.assertRedirects(response, reverse("dashboard"))

    def test_login_rate_limit_applies_to_known_account(self):
        get_user_model().objects.create_user("tester@example.test", "Synthetic-long-password-472!", display_name="Тест")
        for _ in range(12):
            self.client.post(reverse("login"), {"username": "tester@example.test", "password": "wrong"})
        response = self.client.post(reverse("login"), {"username": "tester@example.test", "password": "Synthetic-long-password-472!"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_signup_rate_limit(self):
        for _ in range(8):
            self.client.post(reverse("signup"), self.signup_data(invite_code="wrong"))
        self.assertEqual(self.client.post(reverse("signup"), self.signup_data()).status_code, 429)
        self.assertFalse(get_user_model().objects.exists())

    def test_invalid_invitation_does_not_reveal_duplicate_email(self):
        get_user_model().objects.create_user("existing@example.test", "Synthetic-long-password-472!", display_name="Тест")
        known = self.client.post(reverse("signup"), self.signup_data(email="existing@example.test", invite_code="wrong"))
        unknown = self.client.post(reverse("signup"), self.signup_data(email="unknown@example.test", invite_code="wrong"))
        self.assertEqual(known.context["form"].errors, unknown.context["form"].errors)
        self.assertNotIn("email", known.context["form"].errors)

    def test_weak_password_is_rejected(self):
        self.client.post(reverse("signup"), self.signup_data(password1="12345678", password2="12345678"))
        self.assertFalse(get_user_model().objects.exists())

    def test_all_public_auth_templates_render(self):
        for name in ("login", "signup"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
