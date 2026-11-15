"""Organization workspace shell. Public preview never opens server records."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_GET


@login_required
@require_GET
def app(request):
    return render(request, "organization/app.html", {"organization_demo": False})


@require_GET
def preview(request):
    return render(request, "organization/app.html", {"organization_demo": True})
