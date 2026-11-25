from django.conf import settings


def is_noindex_host(request) -> bool:
    """Return True when the incoming host is a .vercel.app preview/staging domain
    and ALLOW_VERCEL_APP_INDEXING is disabled."""
    host = request.get_host().split(":", 1)[0].lower()
    if host.endswith(".vercel.app") and not getattr(
        settings, "ALLOW_VERCEL_APP_INDEXING", False
    ):
        return True
    return False


class SeoHeadersMiddleware:
    """Emit X-Robots-Tag: noindex, nofollow on .vercel.app hosts so staging/preview
    deployments never compete with durrattarim.com in search results."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if is_noindex_host(request) and "X-Robots-Tag" not in response.headers:
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response
