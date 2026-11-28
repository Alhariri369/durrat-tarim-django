from django.conf import settings
from django.http import HttpResponsePermanentRedirect

SECONDARY_PRODUCTION_HOSTS = frozenset(
    {
        "www.durrattarim.com",
        "durrat-tarim.com",
        "www.durrat-tarim.com",
    }
)

PRIVATE_NOINDEX_PREFIXES = (
    "/admin/",
    "/auth/",
    "/dashboard/",
    "/favorites/",
    "/health/",
)


def is_noindex_host(request) -> bool:
    """Return True when the incoming host is a .vercel.app or dev/staging
    subdomain and ALLOW_VERCEL_APP_INDEXING is disabled."""
    host = request.get_host().split(":", 1)[0].lower()
    if host.startswith(("dev.", "staging.")):
        return True
    if host.endswith(".vercel.app") and not getattr(
        settings, "ALLOW_VERCEL_APP_INDEXING", False
    ):
        return True
    return False


def _private_robots_directive(path: str) -> str:
    """Return an X-Robots-Tag directive for private, search, or action routes,
    or empty string for normal indexable storefront routes."""
    if path.startswith(PRIVATE_NOINDEX_PREFIXES):
        return "noindex, nofollow"
    if path.startswith("/products/items/") and path.endswith(
        ("/whatsapp/", "/favorite/", "/unfavorite/")
    ):
        return "noindex, nofollow"
    if path in ("/search/", "/products/search/"):
        return "noindex, follow"
    return ""


class SeoHeadersMiddleware:
    """Enforce single canonical domain on secondary production aliases and emit
    X-Robots-Tag headers on staging hosts and private/action endpoints."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":", 1)[0].lower()
        canonical_domain = getattr(settings, "CANONICAL_DOMAIN", "").strip().lower()
        if (
            canonical_domain
            and host != canonical_domain
            and host in SECONDARY_PRODUCTION_HOSTS
            and request.method in ("GET", "HEAD")
        ):
            return HttpResponsePermanentRedirect(
                f"https://{canonical_domain}{request.get_full_path()}"
            )

        response = self.get_response(request)
        if "X-Robots-Tag" not in response.headers:
            if is_noindex_host(request):
                response.headers["X-Robots-Tag"] = "noindex, nofollow"
            else:
                directive = _private_robots_directive(request.path)
                if directive:
                    response.headers["X-Robots-Tag"] = directive
        return response
