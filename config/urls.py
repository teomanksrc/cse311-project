from django.contrib import admin
from django.urls import include, path

from accounts.views import home

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("instructor/", include("grading.urls")),
    path("", include("scoring.urls")),
    path("", home, name="home"),
]
