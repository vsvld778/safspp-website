from django.contrib import admin
from django.urls import include, path

urlpatterns = [path("admin/", admin.site.urls), path("", include("portal.urls"))]
admin.site.site_header = "Мост поддержки · Координатор"
admin.site.site_title = "Мост поддержки"
admin.site.index_title = "Обращения и доступ организаций"
