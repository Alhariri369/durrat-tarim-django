from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path, reverse
from django.views.generic import RedirectView

from catalog import views as catalog_views
from catalog.sitemaps import CategorySitemap, ProductSitemap, StaticViewSitemap
from durrat_tarim import sitemap_views

sitemaps = {
    "static": StaticViewSitemap,
    "categories": CategorySitemap,
    "products": ProductSitemap,
}


def robots_txt(request):
    """Serve robots.txt: allow the storefront, keep private/app areas out of
    the index, and point crawlers at the sitemap index."""
    sitemap_url = request.build_absolute_uri(
        reverse("django.contrib.sitemaps.views.index")
    )
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /auth/",
        "Disallow: /dashboard/",
        "Disallow: /favorites/",
        "Disallow: /search/",
        "Disallow: /*?*",
        f"Sitemap: {sitemap_url}",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


urlpatterns = [
    path("", catalog_views.home, name="home"),
    path("health/", catalog_views.health, name="health"),
    path("favorites/", catalog_views.favorites, name="favorites"),
    path(
        "favorites/whatsapp/",
        catalog_views.favorites_whatsapp,
        name="favorites-whatsapp",
    ),
    path("admin/", admin.site.urls),
    path("dashboard/", include("dashboard.urls")),
    path("products/", include("catalog.urls")),
    path("contact/", include("support.urls")),
    path("auth/", include("accounts.urls")),
    path(
        "items/<int:pk>/",
        RedirectView.as_view(pattern_name="product-detail", permanent=True),
    ),
    path("types/", RedirectView.as_view(pattern_name="product-types", permanent=True)),
    path(
        "types/<slug:type_name>/",
        RedirectView.as_view(pattern_name="product-type", permanent=True),
    ),
    path(
        "search/",
        RedirectView.as_view(
            pattern_name="product-search", permanent=True, query_string=True
        ),
    ),
    path(
        "sitemap.xml",
        sitemap_views.index,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.index",
    ),
    path(
        "sitemap-<section>.xml",
        sitemap_views.sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path("robots.txt", robots_txt, name="robots"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
