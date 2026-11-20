"""Sitemaps for the public storefront.

Mounted as /sitemap.xml in durrat_tarim/urls.py. Django serves a sitemap
index there with one sub-sitemap per section below.
"""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Category, Product


class StaticViewSitemap(Sitemap):
    """Fixed pages: home, category index, contact. (Search is excluded on
    purpose — search result pages shouldn't be indexed.)"""

    changefreq = "weekly"

    def items(self):
        return [
            ("home", 1.0),
            ("product-types", 0.8),
            ("contact", 0.4),
        ]

    def location(self, item):
        return reverse(item[0])

    def priority(self, item):
        return item[1]


class CategorySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Category.objects.filter(is_active=True).order_by("pk")

    def location(self, obj):
        return reverse("product-type", kwargs={"type_name": obj.slug})

    def lastmod(self, obj):
        return obj.updated_at


class ProductSitemap(Sitemap):
    # Products are the conversion target — refresh often, rank highest.
    changefreq = "daily"
    priority = 0.9

    def items(self):
        return (
            Product.objects.filter(is_active=True, category__is_active=True)
            .select_related("category")
            .order_by("pk")
        )

    def location(self, obj):
        return reverse("product-detail", args=[obj.pk])

    def lastmod(self, obj):
        return obj.updated_at
