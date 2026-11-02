from django.urls import path

from scoring import views

app_name = "scoring"

urlpatterns = [
    path("student/", views.student_dashboard, name="student_dashboard"),
    path("department/", views.department_dashboard, name="department_dashboard"),
]
