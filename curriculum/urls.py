from django.urls import path

from curriculum import views

app_name = "curriculum"

urlpatterns = [
    path("offerings/<int:offering_id>/", views.offering_setup, name="offering_setup"),
    path("offerings/<int:offering_id>/los/new/", views.lo_form, name="lo_create"),
    path("offerings/<int:offering_id>/los/<int:lo_id>/edit/", views.lo_form, name="lo_edit"),
    path("offerings/<int:offering_id>/los/<int:lo_id>/delete/", views.lo_delete, name="lo_delete"),
    path("offerings/<int:offering_id>/assessments/new/", views.assessment_form, name="assessment_create"),
    path(
        "offerings/<int:offering_id>/assessments/<int:assessment_id>/edit/",
        views.assessment_form,
        name="assessment_edit",
    ),
    path(
        "offerings/<int:offering_id>/assessments/<int:assessment_id>/delete/",
        views.assessment_delete,
        name="assessment_delete",
    ),
    path("offerings/<int:offering_id>/assessment-weights/", views.save_assessment_weights, name="assessment_weights"),
    path("offerings/<int:offering_id>/po-weights/", views.save_po_weights, name="po_weights"),
    path("offerings/<int:offering_id>/syllabus/", views.syllabus_upload, name="syllabus_upload"),
    path("offerings/<int:offering_id>/syllabus/review/", views.syllabus_review, name="syllabus_review"),
    path("offerings/<int:offering_id>/syllabus/apply/", views.syllabus_apply, name="syllabus_apply"),
    path("offerings/<int:offering_id>/syllabus/discard/", views.syllabus_discard, name="syllabus_discard"),
]
