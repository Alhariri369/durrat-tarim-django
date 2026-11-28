from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse

from catalog.models import StoreSettings
from durrat_tarim.middleware import PRIVATE_NOINDEX_PREFIXES, is_noindex_host


def _build_canonical_url(request) -> str:
    """Build a clean canonical URL, stripping tracking query params and
    collapsing ?page=1 while self-canonicalizing ?page=2+ on paginated
    catalog listings."""
    base = f"{request.scheme}://{request.get_host()}{request.path}"
    if request.path == "/products/" or request.path.startswith("/products/types/"):
        raw_page = request.GET.get("page", "")
        if raw_page.isdigit() and int(raw_page) > 1:
            return f"{base}?page={int(raw_page)}"
    return base


def site_context(request):
    store_settings = StoreSettings.get_current()
    user = request.user if request.user.is_authenticated else None
    seo_noindex_host = is_noindex_host(request)
    is_private_route = request.path.startswith(PRIVATE_NOINDEX_PREFIXES)

    ctx = {
        "site_settings": store_settings,
        "store_user": user,
        "is_store_authenticated": bool(user),
        "is_store_admin": bool(user and user.is_staff),
        "account_action_url": reverse("account_logout" if user else "account_login"),
        "account_action_label": "تسجيل الخروج" if user else "تسجيل الدخول",
        "seo_noindex_host": seo_noindex_host,
        "canonical_url": _build_canonical_url(request),
        "default_og_image_url": request.build_absolute_uri(
            static("images/og-default.jpg")
        ),
        "google_site_verification": (
            ""
            if seo_noindex_host
            else getattr(settings, "GOOGLE_SITE_VERIFICATION", "")
        ),
    }
    if is_private_route:
        ctx["robots_content"] = "noindex,nofollow"
    return ctx
