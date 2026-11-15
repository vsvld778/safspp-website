import copy
import json
import uuid
from unittest.mock import patch
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from .admin import OrganizationReplyForm
from .models import Organization, OrganizationMembership, SupportCase, CaseMessage
from .organization_models import (OrganizationWorkspace, OrganizationRequest, OrganizationRequestMessage,
    OrganizationEvent, empty_organization_workspace)


@override_settings(PORTAL_INTAKE_MODE="test", REGISTRATION_MODE="closed")
class OrganizationAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.manager = User.objects.create_user("manager@example.test", "testing", display_name="Орг менеджер")
        cls.editor = User.objects.create_user("editor@example.test", "testing", display_name="Орг редактор")
        cls.viewer = User.objects.create_user("viewer@example.test", "testing", display_name="Наблюдатель")
        cls.outsider = User.objects.create_user("outsider@example.test", "testing", display_name="Посторонний")
        cls.staff = User.objects.create_user("staff@example.test", "testing", display_name="Сотрудник", is_staff=True)
        cls.org = Organization.objects.create(name="Синтетическая НКО", kind="ngo", is_approved=True)
        cls.other_org = Organization.objects.create(name="Другая НКО", kind="ngo", is_approved=True)
        for user, role in [(cls.manager, "manager"), (cls.editor, "editor"), (cls.viewer, "viewer")]:
            OrganizationMembership.objects.create(user=user, organization=cls.org, role=role)
        OrganizationMembership.objects.create(user=cls.outsider, organization=cls.other_org, role="manager")
        cls.org_request = OrganizationRequest.objects.create(organization=cls.org, created_by=cls.manager,
            title="Синтетическая заявка", category="consultation", body="Описание организации", is_test=True)
        cls.support_case = SupportCase.objects.create(owner=cls.outsider, title="Личный секрет", category="other",
            description="Приватное обращение", partner_organization=cls.org, partner_sharing_approved=True,
            partner_consent_record="Синтетическое согласие", partner_summary="Разрешённая задача")

    def setUp(self):
        self.client.force_login(self.manager)

    def url(self, name, org=None, detail=False):
        args = [self.org_request.public_id] if detail else []
        return reverse(name, args=args) + "?organization=" + str((org or self.org).pk)

    def write(self, name, data, method="post", **kwargs):
        return getattr(self.client, method)(self.url(name, **kwargs), json.dumps(data), content_type="application/json")

    def workspace_payload(self, **kwargs):
        data = {"revision": 0, "data": empty_organization_workspace(), "testDataOnly": True}
        data.update(kwargs)
        return data

    def request_payload(self, **kwargs):
        data = {"title": "Тест", "category": "consultation", "body": "Синтетический вопрос", "testDataOnly": True}
        data.update(kwargs)
        return data

    def test_anonymous_api_returns_json_not_login_html(self):
        self.client.logout()
        for name in ("organization_session", "organization_workspace", "organization_requests"):
            response = self.client.get(self.url(name))
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["error"], "authentication_required")
        self.assertEqual(self.write("organization_requests", self.request_payload()).status_code, 401)

    def test_cross_org_reads_and_writes_are_denied(self):
        for name in ("organization_session", "organization_workspace", "organization_requests"):
            self.assertEqual(self.client.get(self.url(name, self.other_org)).status_code, 403)
        self.assertEqual(self.write("organization_workspace", self.workspace_payload(), method="put", org=self.other_org).status_code, 403)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.url("organization_request_detail", self.other_org, True)).status_code, 404)
        self.assertEqual(self.write("organization_request_detail", {"body": "Попытка", "testDataOnly": True}, org=self.other_org, detail=True).status_code, 404)
        self.assertEqual(OrganizationRequestMessage.objects.count(), 0)

    def test_staff_has_no_membership_bypass(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url("organization_session")).status_code, 403)

    def test_membership_and_organization_revocation_apply_immediately(self):
        self.assertEqual(self.client.get(self.url("organization_session")).status_code, 200)
        member = OrganizationMembership.objects.get(user=self.manager)
        member.is_active = False
        member.save()
        self.assertEqual(self.client.get(self.url("organization_workspace")).status_code, 403)
        self.assertEqual(self.write("organization_requests", self.request_payload()).status_code, 403)
        member.is_active = True
        member.save()
        self.org.is_approved = False
        self.org.save()
        self.assertEqual(self.client.get(self.url("organization_request_detail", detail=True)).status_code, 403)

    def test_session_redacts_applicant_and_account_data(self):
        response = self.client.get(self.url("organization_session"))
        data = response.json()
        self.assertEqual(data["membership"], {"role": "manager"})
        self.assertTrue(data["capabilities"]["canManage"])
        self.assertEqual(data["cases"][0]["summary"], "Разрешённая задача")
        for secret in ("Личный секрет", "Приватное обращение", "outsider@example.test", "manager@example.test", "Синтетическое согласие"):
            self.assertNotIn(secret, json.dumps(data, ensure_ascii=False))
        self.assertIn("no-store", response["Cache-Control"])

    def test_employer_and_staffing_never_access_personal_cases(self):
        for kind in ("employer", "staffing"):
            self.org.kind = kind
            self.org.save()
            self.assertEqual(self.client.get(self.url("organization_session")).json()["cases"], [])
            self.assertEqual(self.client.get(reverse("partner_case_detail", args=[self.support_case.public_id])).status_code, 404)
            self.support_case.refresh_from_db()
            with self.assertRaises(ValidationError):
                self.support_case.full_clean()

    def test_viewer_is_read_only_in_api_and_legacy_case_route(self):
        self.client.force_login(self.viewer)
        self.assertFalse(self.client.get(self.url("organization_session")).json()["capabilities"]["canWrite"])
        self.assertEqual(self.client.get(self.url("organization_request_detail", detail=True)).status_code, 200)
        self.assertEqual(self.write("organization_workspace", self.workspace_payload(), method="put").status_code, 403)
        self.assertEqual(self.write("organization_requests", self.request_payload()).status_code, 403)
        self.assertEqual(self.write("organization_request_detail", {"body": "Нет", "testDataOnly": True}, detail=True).status_code, 403)
        self.assertEqual(self.client.post(reverse("partner_case_detail", args=[self.support_case.public_id]), {"body": "Нет"}).status_code, 403)
        self.assertEqual(CaseMessage.objects.count(), 0)

    def test_editor_can_write_projects_but_cannot_change_profile(self):
        self.client.force_login(self.editor)
        payload = self.workspace_payload()
        payload["data"]["profile"]["city"] = "Тест"
        self.assertEqual(self.write("organization_workspace", payload, method="put").status_code, 403)
        payload["data"]["profile"]["city"] = ""
        payload["data"]["projects"] = [{"id": str(uuid.uuid4()), "title": "Проект", "description": "Тест", "status": "planned", "deadline": ""}]
        self.assertEqual(self.write("organization_workspace", payload, method="put").status_code, 200)
        self.assertEqual(OrganizationWorkspace.objects.get().revision, 1)

    def test_workspace_persists_and_stale_update_cannot_overwrite(self):
        payload = self.workspace_payload()
        payload["data"]["profile"]["city"] = "Тестовый город"
        self.assertEqual(self.write("organization_workspace", payload, method="put").json()["revision"], 1)
        payload["data"]["profile"]["city"] = "Затёртый город"
        response = self.write("organization_workspace", payload, method="put")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "revision_conflict")
        self.assertEqual(self.client.get(self.url("organization_workspace")).json()["data"]["profile"]["city"], "Тестовый город")
        self.assertEqual(OrganizationEvent.objects.get().detail["revision"], 1)

    def test_workspace_rejects_unknown_authority_fields_and_bad_types(self):
        for key in ("members", "roles", "requests", "isApproved"):
            payload = self.workspace_payload()
            payload["data"][key] = []
            self.assertEqual(self.write("organization_workspace", payload, method="put").status_code, 400)
        for revision in (True, -1, "0"):
            self.assertEqual(self.write("organization_workspace", self.workspace_payload(revision=revision), method="put").status_code, 400)
        self.assertEqual(OrganizationWorkspace.objects.count(), 0)

    def test_workspace_validates_https_ids_links_and_array_limits(self):
        good = self.workspace_payload()
        good["data"]["documents"] = [{"id": str(uuid.uuid4()), "title": "Шаблон", "category": "template", "url": "https://example.test/template", "note": "", "projectId": ""}]
        for url in ("javascript:alert(1)", "http://example.test", "https://user:password@example.test"):
            payload = copy.deepcopy(good)
            payload["data"]["documents"][0]["url"] = url
            self.assertEqual(self.write("organization_workspace", payload, method="put").status_code, 400)
        payload = copy.deepcopy(good)
        payload["data"]["documents"][0]["projectId"] = str(uuid.uuid4())
        self.assertEqual(self.write("organization_workspace", payload, method="put").status_code, 400)
        payload = copy.deepcopy(good)
        payload["data"]["documents"] *= 101
        self.assertEqual(self.write("organization_workspace", payload, method="put").status_code, 400)
        self.assertEqual(self.write("organization_workspace", good, method="put").status_code, 200)

    def test_json_size_duplicates_depth_and_string_limits(self):
        url = self.url("organization_workspace")
        for raw in ('{"revision":0,"revision":1,"data":{}}', '{"revision":NaN}', '[' * 1200 + ']' * 1200):
            self.assertEqual(self.client.put(url, raw, content_type="application/json").status_code, 400)
        self.assertEqual(self.client.put(url, ' ' * (96 * 1024 + 1), content_type="application/json").status_code, 413)
        payload = self.workspace_payload()
        payload["data"]["profile"]["description"] = "x" * 3001
        self.assertEqual(self.write("organization_workspace", payload, method="put").status_code, 400)

    def test_request_author_org_status_and_audience_are_server_controlled(self):
        for key in ("organization", "organizationId", "created_by", "status", "audience", "isTest", "author"):
            self.assertEqual(self.write("organization_requests", self.request_payload(**{key: "injected"})).status_code, 400)
        response = self.write("organization_requests", self.request_payload())
        self.assertEqual(response.status_code, 201)
        item = OrganizationRequest.objects.get(public_id=response.json()["request"]["id"])
        self.assertEqual(item.organization, self.org)
        self.assertEqual(item.created_by, self.manager)
        self.assertEqual(item.status, "new")
        self.assertTrue(item.is_test)
        self.assertEqual(item.policy_version, "synthetic-test")
        self.assertEqual(item.events.get().event_type, "request_created")

    def test_request_foreign_project_is_rejected(self):
        project_id = str(uuid.uuid4())
        data = empty_organization_workspace()
        data["projects"] = [{"id": project_id, "title": "Чужой проект"}]
        OrganizationWorkspace.objects.create(organization=self.other_org, data=data)
        self.assertEqual(self.write("organization_requests", self.request_payload(projectId=project_id)).status_code, 404)

    def test_messages_are_real_scoped_and_cannot_impersonate_staff(self):
        for extra in ({"author": self.staff.pk}, {"isStaff": True}, {"audience": "internal"}):
            self.assertEqual(self.write("organization_request_detail", {"body": "Сообщение", "testDataOnly": True, **extra}, detail=True).status_code, 400)
        response = self.write("organization_request_detail", {"body": "Сообщение", "testDataOnly": True}, detail=True)
        self.assertEqual(response.status_code, 201)
        message = OrganizationRequestMessage.objects.get()
        self.assertEqual(message.author, self.manager)
        self.assertFalse(message.is_staff_reply)
        self.assertEqual(response.json()["messages"][0]["isOwn"], True)
        self.assertEqual(OrganizationEvent.objects.get().event_type, "message_added")

    def test_closed_request_rejects_messages(self):
        for status in ("closed", "resolved"):
            self.org_request.status = status
            self.org_request.save()
            self.assertEqual(self.write("organization_request_detail", {"body": "Нет", "testDataOnly": True}, detail=True).status_code, 409)
        self.assertEqual(OrganizationRequestMessage.objects.count(), 0)

    def test_test_mode_requires_explicit_confirmation(self):
        self.assertEqual(self.write("organization_workspace", {"revision": 0, "data": empty_organization_workspace()}, method="put").status_code, 400)
        self.assertEqual(self.write("organization_requests", self.request_payload(testDataOnly=False)).status_code, 400)
        self.assertEqual(self.write("organization_request_detail", {"body": "Нет"}, detail=True).status_code, 400)

    @override_settings(PORTAL_INTAKE_MODE="disabled")
    def test_disabled_intake_denies_all_mutations(self):
        self.assertEqual(self.client.get(self.url("organization_workspace")).status_code, 200)
        self.assertFalse(self.client.get(self.url("organization_session")).json()["capabilities"]["canWrite"])
        self.assertEqual(self.write("organization_workspace", self.workspace_payload(), method="put").status_code, 403)
        self.assertEqual(self.write("organization_requests", self.request_payload()).status_code, 403)
        self.assertEqual(self.write("organization_request_detail", {"body": "Нет"}, detail=True).status_code, 403)

    @override_settings(PORTAL_INTAKE_MODE="live", PORTAL_POLICY_VERSION="test-policy")
    def test_live_request_requires_consent_and_records_policy(self):
        self.assertEqual(self.write("organization_requests", self.request_payload()).status_code, 400)
        response = self.write("organization_requests", self.request_payload(privacyConsent=True))
        item = OrganizationRequest.objects.get(public_id=response.json()["request"]["id"])
        self.assertFalse(item.is_test)
        self.assertEqual(item.policy_version, "test-policy")
        self.assertIsNotNone(item.consented_at)

    def test_rate_limit_returns_json_429(self):
        with patch("portal.organization_api.allow_request", return_value=False):
            self.assertEqual(self.write("organization_requests", self.request_payload()).status_code, 429)

    def test_csrf_and_foreign_origin_rejected_for_real_client(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.manager)
        token = self.client.get(self.url("organization_session")).json()["csrfToken"]
        data = json.dumps(self.workspace_payload())
        self.assertEqual(self.client.put(self.url("organization_workspace"), data, content_type="application/json").status_code, 403)
        self.assertEqual(self.client.put(self.url("organization_workspace"), data, content_type="application/json", HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="https://evil.example").status_code, 403)
        self.assertEqual(self.client.put(self.url("organization_workspace"), data, content_type="application/json", HTTP_X_CSRFTOKEN=token).status_code, 200)

    def test_admin_reply_is_audited_and_role_cannot_enter_admin(self):
        self.assertEqual(self.client.get(reverse("admin:portal_organizationrequest_changelist")).status_code, 302)
        request = RequestFactory().post("/admin/")
        request.user = self.staff
        message = OrganizationRequestMessage(request=self.org_request, body="Ответ фонда")
        registered = admin.site._registry[OrganizationRequestMessage]
        registered.save_model(request, message, None, False)
        self.assertEqual(message.author, self.staff)
        self.assertTrue(message.is_staff_reply)
        response = self.client.get(self.url("organization_request_detail", detail=True)).json()
        self.assertEqual(response["messages"][0]["authorName"], "Координатор фонда")
        self.assertTrue(response["messages"][0]["isStaff"])
        self.assertEqual(OrganizationEvent.objects.get().event_type, "staff_message")
        self.org_request.status = "closed"
        self.org_request.save()
        self.assertFalse(OrganizationReplyForm({"request": self.org_request.pk, "body": "Нет"}).is_valid())

    def test_admin_workspace_and_history_cannot_be_rewritten(self):
        request = RequestFactory().get("/admin/")
        request.user = self.staff
        for model in (OrganizationWorkspace, OrganizationEvent, OrganizationRequestMessage):
            registered = admin.site._registry[model]
            self.assertFalse(registered.has_change_permission(request))
            self.assertFalse(registered.has_delete_permission(request))
