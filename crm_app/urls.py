from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("", views.home_view, name="home"),
    # Projects
    path("projects/", views.project_list_view, name="project_list"),
    path("projects/new/", views.project_create_view, name="project_create"),
    path("projects/import/", views.import_projects_view, name="import_projects"),
    path(
        "projects/wizard/save/", views.project_wizard_save, name="project_wizard_save"
    ),
    path("projects/save_section/", views.project_form_save_section, name="project_form_save_section"),
    path("projects/<int:pk>/save_section/", views.project_form_save_section, name="project_form_save_section_pk"),
    path("projects/<int:pk>/", views.project_detail_view, name="project_detail"),
    path("projects/<int:pk>/edit/", views.project_create_view, name="project_update"),
    path("projects/<int:pk>/duplicate/", views.duplicate_project_view, name="project_duplicate"),
    path(
        "projects/<int:pk>/phase/",
        views.project_phase_update_view,
        name="project_phase_update",
    ),
    path(
        "projects/<int:pk>/checklist/import/",
        views.checklist_import_view,
        name="checklist_import",
    ),
    path(
        "projects/<int:pk>/checklist.pdf",
        views.project_checklist_pdf_view,
        name="project_checklist_pdf",
    ),
    # Checklist item actions
    path(
        "checklist/item/<int:item_id>/add-note/",
        views.checklist_item_add_note_view,
        name="checklist_item_add_note",
    ),
    path(
        "checklist/item/<int:item_id>/toggle/",
        views.checklist_item_toggle_view,
        name="checklist_item_toggle",
    ),
    # Other pages
    path("profile/", views.profile_view, name="profile"),
    path("team/", views.team_dashboard_view, name="team_dashboard"),
    path("search/", views.search_view, name="search"),
    path("analytics/", views.analytics_view, name="analytics"),
    path("coordination/form/", views.coordination_form_view, name="coordination_form"),
    path(
        "coordination/form/<int:pk>/",
        views.coordination_form_view,
        name="coordination_form_edit",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
