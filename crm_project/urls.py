from django.contrib import admin
from django.urls import path, include
from crm_app.views import project_phase_update_view


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('crm_app.urls')),
    path('projects/<int:pk>/phase/', project_phase_update_view, name='project_phase_update'),

]
