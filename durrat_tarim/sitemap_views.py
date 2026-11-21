"""Request-aware replacements for Django's stock sitemap views.

The stock views resolve absolute URLs through ``django.contrib.sites``
(``SITE_ID`` -> ``Site.domain``), which is ``example.com`` in this project.
That would publish a sitemap full of the wrong domain. These wrappers build
URLs from the incoming request host instead (``RequestSite``), so the sitemap
matches whatever domain the storefront is actually served from.
"""

import datetime
from dataclasses import dataclass

from django.contrib.sites.requests import RequestSite
from django.core.paginator import EmptyPage, PageNotAnInteger
from django.http import Http404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.http import http_date


@dataclass
class SitemapIndexItem:
    location: str
    last_mod: datetime.datetime | None = None


def _latest_lastmod(current, new):
    if not isinstance(new, datetime.datetime):
        new = datetime.datetime.combine(new, datetime.time.min)
    if timezone.is_naive(new):
        new = timezone.make_aware(new, datetime.UTC)
    return new if current is None else max(current, new)


def index(
    request,
    sitemaps,
    template_name="sitemap_index.xml",
    content_type="application/xml",
    sitemap_url_name="django.contrib.sitemaps.views.sitemap",
):
    protocol = request.scheme
    site = RequestSite(request)

    entries = []
    all_lastmod = True
    latest = None
    for section, sitemap_class in sitemaps.items():
        if callable(sitemap_class):
            sitemap_class = sitemap_class()
        section_protocol = protocol if sitemap_class.protocol is None else sitemap_class.protocol
        sitemap_url = reverse(sitemap_url_name, kwargs={"section": section})
        absolute_url = f"{section_protocol}://{site.domain}{sitemap_url}"
        lastmod = sitemap_class.get_latest_lastmod()
        if all_lastmod:
            if lastmod is not None:
                latest = _latest_lastmod(latest, lastmod)
            else:
                all_lastmod = False
        entries.append(SitemapIndexItem(absolute_url, lastmod))
        for page in range(2, sitemap_class.paginator.num_pages + 1):
            entries.append(SitemapIndexItem(f"{absolute_url}?p={page}", lastmod))

    headers = {"Last-Modified": http_date(latest.timestamp())} if all_lastmod and latest else None
    response = TemplateResponse(
        request, template_name, {"sitemaps": entries}, content_type=content_type, headers=headers
    )
    response.headers["X-Robots-Tag"] = "noindex, noodp, noarchive"
    return response


def sitemap(
    request,
    sitemaps,
    section=None,
    template_name="sitemap.xml",
    content_type="application/xml",
):
    protocol = request.scheme
    site = RequestSite(request)

    if section is not None:
        if section not in sitemaps:
            raise Http404(f"No sitemap available for section: {section!r}")
        maps = [sitemaps[section]]
    else:
        maps = sitemaps.values()
    page = request.GET.get("p", 1)

    urls = []
    all_lastmod = True
    latest = None
    for sitemap_class in maps:
        try:
            if callable(sitemap_class):
                sitemap_class = sitemap_class()
            urls.extend(sitemap_class.get_urls(page=page, site=site, protocol=protocol))
            if all_lastmod:
                lastmod = getattr(sitemap_class, "latest_lastmod", None)
                if lastmod is not None:
                    latest = _latest_lastmod(latest, lastmod)
                else:
                    all_lastmod = False
        except EmptyPage:
            raise Http404(f"Page {page} empty")
        except PageNotAnInteger:
            raise Http404(f"No page '{page}'")

    headers = {"Last-Modified": http_date(latest.timestamp())} if all_lastmod and latest else None
    response = TemplateResponse(
        request, template_name, {"urlset": urls}, content_type=content_type, headers=headers
    )
    response.headers["X-Robots-Tag"] = "noindex, noodp, noarchive"
    return response
