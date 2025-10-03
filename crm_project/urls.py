from django.conf import settings
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from crm_app.views import project_phase_update_view, microsoft_login_view, microsoft_callback_view


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("crm_app.urls")),
    path(
        "projects/<int:pk>/phase/",
        project_phase_update_view,
        name="project_phase_update",
    ),
    # Microsoft Authentication URLs
    path("microsoft-auth/login/", microsoft_login_view, name="microsoft_login"),
    re_path(r"^microsoft-auth/callback/$", microsoft_callback_view, name="microsoft_callback"),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns = [
        path("__debug__/", include(debug_toolbar.urls)),
    ] + urlpatterns
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
