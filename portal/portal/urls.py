from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.PortalLoginView.as_view(), name="login"),
    path("logout/", views.PortalLogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
    path("cases/", views.dashboard, name="dashboard"),
    path("cases/new/", views.case_create, name="case_create"),
    path("cases/<uuid:public_id>/", views.case_detail, name="case_detail"),
    path("partners/", views.partner_dashboard, name="partner_dashboard"),
    path("partners/cases/<uuid:public_id>/", views.partner_case_detail, name="partner_case_detail"),
    path("healthz/", views.healthz, name="healthz"),
]
