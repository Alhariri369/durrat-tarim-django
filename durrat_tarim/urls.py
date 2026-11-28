from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.templatetags.static import static as static_url
from django.urls import include, path, reverse
from django.views.generic import RedirectView

from catalog import views as catalog_views
from catalog.models import Category, Product, StoreSettings
from catalog.sitemaps import CategorySitemap, ProductSitemap, StaticViewSitemap
from durrat_tarim import sitemap_views
from durrat_tarim.middleware import is_noindex_host

handler404 = "durrat_tarim.views.error_404"

sitemaps = {
    "static": StaticViewSitemap,
    "categories": CategorySitemap,
    "products": ProductSitemap,
}


def robots_txt(request):
    """Serve robots.txt: block indexing on .vercel.app preview/staging hosts,
    otherwise allow the storefront, keep private/app/search areas out of the
    index, and point crawlers at the sitemap index."""
    if is_noindex_host(request):
        return HttpResponse(
            "User-agent: *\nDisallow: /\n", content_type="text/plain"
        )

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
        "Disallow: /health/",
        "Disallow: /search/",
        "Disallow: /products/search/",
        "Disallow: /products/items/*/whatsapp/",
        "Disallow: /products/items/*/favorite/",
        "Disallow: /products/items/*/unfavorite/",
        "Disallow: /*?q=*",
        "Disallow: /*?product_desc=*",
        f"Sitemap: {sitemap_url}",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def llms_txt(request):
    """Serve llms.txt for AI search engines and agents (ChatGPT, Perplexity,
    Claude) with verified store identity, active category tree, sample SAR
    pricing, and canonical URLs."""
    base_url = f"{request.scheme}://{request.get_host()}"
    store_settings = StoreSettings.get_current()
    whatsapp = (
        getattr(store_settings, "whatsapp_number", "") or "967783278181"
    ).lstrip("+")
    local_phone = getattr(store_settings, "local_phone", "") or "783278181"
    sar_rate = getattr(store_settings, "sar_to_yer_rate", "") or "410"
    address_ar = (
        getattr(store_settings, "address_ar", "") or "سوق الفتح، تريم، وادي حضرموت، اليمن"
    )
    active_ids = Category.active_category_ids()
    ordered_categories = Category.tree_ordered_categories(
        Category.objects.filter(id__in=active_ids).select_related("parent")
    )
    latest_products = list(
        Product.objects.filter(is_active=True, category_id__in=active_ids)
        .select_related("category")
        .order_by("-created_at", "-id")[:12]
    )

    lines = [
        "# درة تريم (Durrat Tarim)",
        "",
        "> متجر درة تريم للقطع العرائسية والأقمشة الفاخرة والأزياء النسائية الراقية في سوق الفتح، تريم، وادي حضرموت، اليمن. أسعار معلنة بالريال السعودي (SAR) وما يعادلها بالريال اليمني (YER) مع استشارة وطلب مباشر عبر واتساب.",
        "",
        "## Store Facts",
        "- Brand: درة تريم (Durrat Tarim)",
        f"- Website: {base_url}/",
        f"- Showroom Address: {address_ar} (16.05294, 48.97709)",
        "- Service Area: تريم، سيئون، وادي حضرموت، وشحن إلى محافظات اليمن بالتنسيق عبر واتساب",
        f"- WhatsApp Concierge: https://wa.me/{whatsapp} (+{whatsapp})",
        f"- Local Phone: +967 {local_phone}",
        "- Opening Hours: Saturday-Thursday 09:00-21:30, Friday 16:00-22:00 (Asia/Riyadh)",
        f"- Pricing & Currencies: Prices listed in SAR with live YER conversion (reference rate: 1 SAR ≈ {sar_rate} YER)",
        "- Payment Methods: In-store cash, bank transfer, or approved currency exchange companies (شركات الصرافة المعتمدة)",
        "- Returns & Exchanges: Return within 1 day; exchange within 3 days of receipt in original condition via WhatsApp",
        "- Ordering Flow: Browse catalog -> tap WhatsApp inquiry on a single item or batch-select multiple saved items from Favorites -> confirm size, availability, payment, and delivery on WhatsApp",
        "",
        "## Key Pages",
        f"- [الرئيسية (Home)]({base_url}{reverse('home')}): Featured pieces, categories, latest arrivals, and FAQs",
        f"- [جميع المنتجات (All Products)]({base_url}{reverse('product-list')}): Full paginated product catalog with SAR/YER pricing",
        f"- [التصنيفات (Categories)]({base_url}{reverse('product-types')}): Browse collections by category",
        f"- [اتصل بنا (Contact)]({base_url}{reverse('contact')}): Showroom map, working hours, WhatsApp, phone, and support form",
        f"- [XML Sitemap]({base_url}{reverse('django.contrib.sitemaps.views.index')}): Complete index of public pages, categories, and products",
        "",
    ]

    if ordered_categories:
        lines.append("## Active Categories")
        for category in ordered_categories:
            cat_url = f"{base_url}{reverse('product-type', args=[category.slug])}"
            indent = "  " * category.depth
            label = (
                f"{category.name_ar} ({category.name_en})"
                if category.name_en
                else category.name_ar
            )
            lines.append(f"{indent}- [{label}]({cat_url})")
        lines.append("")

    if latest_products:
        lines.append("## Latest Available Pieces (SAR)")
        for prod in latest_products:
            prod_url = f"{base_url}{reverse('product-detail', args=[prod.pk])}"
            label = (
                f"{prod.name_ar} ({prod.name_en})" if prod.name_en else prod.name_ar
            )
            lines.append(
                f"- [{label}]({prod_url}): {prod.price_sar} SAR — {prod.category.name_ar}"
            )
        lines.append("")

    lines.extend(
        [
            "## Official Social Profiles",
            "- Instagram: https://www.instagram.com/durttrim/",
            "- Snapchat: https://www.snapchat.com/add/durttrim",
            "- TikTok: https://www.tiktok.com/@durttrim",
            "",
        ]
    )

    return HttpResponse(
        "\n".join(lines), content_type="text/plain; charset=utf-8"
    )


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
    path("llms.txt", llms_txt, name="llms-txt"),
    path(
        "favicon.ico",
        RedirectView.as_view(url=static_url("images/favicon.png"), permanent=True),
        name="favicon",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
