from django.urls import path

from alerts import views

app_name = "alerts"

urlpatterns = [
    path("send/", views.send_alerts, name="send"),
]
