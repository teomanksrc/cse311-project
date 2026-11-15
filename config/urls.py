from django.contrib import admin
from django.urls import include, path

from accounts.views import home

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("instructor/setup/", include("curriculum.urls")),
    path("instructor/", include("grading.urls")),
    path("reports/", include("reporting.urls")),
    path("alerts/", include("alerts.urls")),
    path("", include("scoring.urls")),
    path("", home, name="home"),
]
