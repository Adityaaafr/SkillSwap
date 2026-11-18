from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.templatetags.static import static as static_url
from django.urls import include, path
from django.views.generic import RedirectView

admin.site.site_header = "SkillSwap administration"
admin.site.site_title = "SkillSwap admin"
admin.site.index_title = "Manage users, skills and exchanges"

urlpatterns = [
    # Browsers ask for /favicon.ico on their own; point them at the SVG icon.
    path("favicon.ico", RedirectView.as_view(url=static_url("favicon.svg"), permanent=True)),
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("", include("accounts.urls")),
    path("", include("skills.urls")),
    path("", include("exchange.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
