from django.urls import path

from grading import views

app_name = "grading"

urlpatterns = [
    path("", views.instructor_home, name="instructor_home"),
    path("assessments/<int:assessment_id>/grades/", views.enter_grades, name="enter_grades"),
]
