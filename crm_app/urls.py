from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    path('', views.home_view, name='home'),

    # Projects
    path('projects/', views.project_list_view, name='project_list'),
    path('projects/new/', views.project_create_view, name='project_create'),
    path('projects/<int:pk>/', views.project_detail_view, name='project_detail'),
    path('projects/<int:pk>/phase/', views.project_phase_update_view, name='project_phase_update'),  # ← added
    path('projects/<int:pk>/checklist/import/', views.checklist_import_view, name='checklist_import'),
    path('projects/<int:pk>/checklist.pdf', views.project_checklist_pdf_view, name='project_checklist_pdf'),

    # Checklist item actions
    path('checklist/item/<int:item_id>/add-note/', views.checklist_item_add_note_view, name='checklist_item_add_note'),
    path('checklist/item/<int:item_id>/toggle/', views.checklist_item_toggle_view, name='checklist_item_toggle'),

    # Other pages
    path('profile/', views.profile_view, name='profile'),
    path('team/', views.team_dashboard_view, name='team_dashboard'),
    path('search/', views.search_view, name='search'),
    path('analytics/', views.analytics_view, name='analytics'),
    # Optional: path('geo/', views.geo_overview, name='geo_overview'),
]

# Serve media files in dev
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
