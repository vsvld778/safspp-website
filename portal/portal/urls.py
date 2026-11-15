from django.urls import path
from . import views, organization_api, organization_ui

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.PortalLoginView.as_view(), name="login"),
    path("logout/", views.PortalLogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
    path("cases/", views.dashboard, name="dashboard"),
    path("cases/new/", views.case_create, name="case_create"),
    path("cases/<uuid:public_id>/", views.case_detail, name="case_detail"),
    path("partners/", organization_ui.app, name="partner_dashboard"),
    path("partners/preview/", organization_ui.preview, name="organization_preview"),
    path("partners/api/session/", organization_api.session, name="organization_session"),
    path("partners/api/workspace/", organization_api.workspace, name="organization_workspace"),
    path("partners/api/requests/", organization_api.requests, name="organization_requests"),
    path("partners/api/requests/<uuid:public_id>/", organization_api.request_item, name="organization_request_detail"),
    path("partners/cases/<uuid:public_id>/", views.partner_case_detail, name="partner_case_detail"),
    path("healthz/", views.healthz, name="healthz"),
]
