from types import SimpleNamespace
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied
from django.db import transaction, connection
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods
from .access import approved_organizations, partner_cases
from .forms import CaseMessageForm, EmailAuthenticationForm, SignupForm, SupportCaseForm
from .models import CaseEvent, CaseMessage, SupportCase
from .ratelimit import allow_request, client_ip

class PortalLoginView(LoginView):
    authentication_form = EmailAuthenticationForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True

class PortalLogoutView(LogoutView):
    http_method_names = ["post", "options"]

@require_GET
def home(request):
    return redirect("dashboard" if request.user.is_authenticated else "login")

@require_http_methods(["GET", "POST"])
def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if settings.REGISTRATION_MODE == "closed":
        return render(request, "portal/registration_closed.html", status=403)
    form = SignupForm(request.POST or None)
    if request.method == "POST":
        if not allow_request("signup", client_ip(request), 8, 3600):
            form.add_error(None, "Слишком много попыток. Повторите позже.")
            return render(request, "registration/signup.html", {"form": form}, status=429)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
            login(request, user, backend="portal.auth.ThrottledEmailBackend")
            messages.success(request, "Кабинет создан. Email указан для связи; его подтверждение пока не выполнялось.")
            return redirect("dashboard")
    return render(request, "registration/signup.html", {"form": form})

@login_required
@require_GET
def dashboard(request):
    cases = SupportCase.objects.filter(owner=request.user)
    stats = cases.aggregate(total=Count("id"), active=Count("id", filter=~Q(status__in=["resolved", "closed"])),
        waiting=Count("id", filter=Q(status="waiting")), resolved=Count("id", filter=Q(status__in=["resolved", "closed"])))
    return render(request, "portal/dashboard.html", {"cases": cases[:100], "stats": stats})

@login_required
@require_http_methods(["GET", "POST"])
def case_create(request):
    if settings.PORTAL_INTAKE_MODE == "disabled":
        messages.info(request, "Приём обращений ещё не открыт.")
        return redirect("dashboard")
    form = SupportCaseForm(request.POST or None, initial={"preferred_language": request.user.preferred_language})
    if request.method == "POST":
        if not allow_request("case-create", str(request.user.pk), 8, 3600):
            form.add_error(None, "Слишком много обращений за короткое время. Повторите позже.")
            return render(request, "portal/case_form.html", {"form": form}, status=429)
        if form.is_valid():
            with transaction.atomic():
                case = form.save(commit=False)
                case.owner = request.user
                case.is_test = settings.PORTAL_INTAKE_MODE == "test"
                case.policy_version = "synthetic-test" if case.is_test else settings.PORTAL_POLICY_VERSION
                case.consented_at = timezone.now()
                case.save()
                CaseEvent.objects.create(case=case, actor=request.user, event_type="created", detail={"test": case.is_test})
            messages.success(request, "Тестовое обращение сохранено." if case.is_test else "Обращение сохранено. Его номер доступен в кабинете.")
            return redirect(case)
    return render(request, "portal/case_form.html", {"form": form})

def add_message(request, case, audience, form):
    if settings.PORTAL_INTAKE_MODE == "disabled":
        form.add_error(None, "Приём сообщений сейчас приостановлен.")
        return False
    if case.status in {SupportCase.Status.RESOLVED, SupportCase.Status.CLOSED}:
        form.add_error(None, "Переписка по завершённому обращению закрыта.")
        return False
    if not allow_request("case-message", str(request.user.pk), 30, 600):
        form.add_error(None, "Слишком много сообщений. Повторите позже.")
        return False
    if form.is_valid():
        with transaction.atomic():
            message = form.save(commit=False)
            message.case = case
            message.author = request.user
            message.audience = audience
            if audience == CaseMessage.Audience.PARTNER:
                message.partner_organization = case.partner_organization
            message.save()
            SupportCase.objects.filter(pk=case.pk).update(updated_at=timezone.now())
            CaseEvent.objects.create(case=case, actor=request.user, event_type="message_added", detail={"audience": audience})
        messages.success(request, "Сообщение сохранено.")
        return True
    return False

@login_required
@require_http_methods(["GET", "POST"])
def case_detail(request, public_id):
    # Staff use the audited admin. An ordinary cabinet always shows its owner's cases only.
    case = get_object_or_404(SupportCase, public_id=public_id, owner=request.user)
    form = CaseMessageForm(request.POST or None)
    if request.method == "POST" and add_message(request, case, CaseMessage.Audience.APPLICANT, form):
        return redirect(case)
    thread = case.messages.exclude(audience=CaseMessage.Audience.INTERNAL).select_related("author")
    return render(request, "portal/case_detail.html", {"case": case, "case_messages": thread, "form": form})

def partner_case_presentation(case):
    # Do not pass the ORM object into partner templates: it could expose private fields.
    return SimpleNamespace(reference=case.reference, public_id=case.public_id, status=case.status,
        get_status_display=case.get_status_display(), partner_summary=case.partner_summary,
        partner_next_step=case.partner_next_step, updated_at=case.updated_at, is_test=case.is_test,
        get_absolute_url=reverse("partner_case_detail", kwargs={"public_id": case.public_id}))

@login_required
@require_GET
def partner_dashboard(request):
    organizations = approved_organizations(request.user)
    cases = [partner_case_presentation(case) for case in partner_cases(request.user)[:100]]
    return render(request, "portal/partner_dashboard.html", {"organizations": organizations, "cases": cases})

@login_required
@require_http_methods(["GET", "POST"])
def partner_case_detail(request, public_id):
    case = get_object_or_404(partner_cases(request.user), public_id=public_id)
    form = CaseMessageForm(request.POST or None)
    if request.method == "POST" and add_message(request, case, CaseMessage.Audience.PARTNER, form):
        return redirect("partner_case_detail", public_id=case.public_id)
    thread = [SimpleNamespace(body=message.body, author_display=message.author_display,
        audience=message.audience, created_at=message.created_at, is_own=message.author_id == request.user.pk)
        for message in case.messages.filter(audience=CaseMessage.Audience.PARTNER,
            partner_organization=case.partner_organization).select_related("author")]
    return render(request, "portal/partner_case_detail.html", {"case": partner_case_presentation(case), "case_messages": thread, "form": form})

@require_GET
def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
