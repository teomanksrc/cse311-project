from django.urls import path

from reporting import views

app_name = "reporting"

urlpatterns = [
    path("me/", views.my_report, name="my_report"),
    path("students/", views.student_list, name="student_list"),
    path("students/<int:student_id>/", views.student_report, name="student_report"),
]
