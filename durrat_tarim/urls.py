from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin as django_admin
from django.urls import include, path
from django.views.generic import RedirectView

from catalog import views as catalog_views

urlpatterns = [
    path("", catalog_views.home, name="home"),
    path("health", catalog_views.health, name="health"),
    path("django-admin/", django_admin.site.urls),
    path("products/", include("catalog.urls")),
    path("contact", include("support.urls")),
    path("contact/", include("support.urls")),
    path("auth/", include("accounts.urls")),
    path("admin/", include("catalog.admin_urls")),
    path("items/<int:pk>", RedirectView.as_view(pattern_name="product-detail", permanent=True)),
    path("types", RedirectView.as_view(pattern_name="product-types", permanent=True)),
    path("types/<str:type_name>", RedirectView.as_view(pattern_name="product-type", permanent=True)),
    path("search", RedirectView.as_view(pattern_name="product-search", permanent=True, query_string=True)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
