import json

from django import template
from django.urls import reverse
from django.utils.safestring import mark_safe

from catalog.currency import format_sar, format_yer

register = template.Library()

# Currency filters used across the storefront templates.
register.filter("format_sar", format_sar)
register.filter("format_yer", format_yer)


def _json_ld(data):
    """Serialize structured data so it is safe to embed in a <script> tag.

    ``</`` is escaped so user-provided text can never close the script tag
    early, and the result is marked safe so Django does not HTML-escape the
    JSON (which would turn quotes into ``&quot;`` and invalidate it).
    """
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    return mark_safe(payload.replace("</", "<\\/"))


def _absolute_uri(request, path):
    return request.build_absolute_uri(path)


@register.inclusion_tag("catalog/partials/product_json_ld.html", takes_context=True)
def product_json_ld(context, product):
    """Render Product JSON-LD. Usage: {% product_json_ld product %}"""
    request = context["request"]
    url = _absolute_uri(request, reverse("product-detail", args=[product.pk]))
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product.name_ar,
        "description": (product.description_ar or product.name_ar)[:5000],
        "sku": product.slug,
        "url": url,
        "brand": {"@type": "Brand", "name": "درّة تريم"},
        "offers": {
            "@type": "Offer",
            "url": url,
            "price": str(product.price_sar),
            "priceCurrency": "SAR",
            "availability": "https://schema.org/InStock",
            "itemCondition": "https://schema.org/NewCondition",
        },
    }
    if product.category_id:
        data["category"] = product.category.full_path
    if product.image:
        data["image"] = [_absolute_uri(request, product.image.url)]
    return {"json_ld": _json_ld(data)}


@register.inclusion_tag("catalog/partials/category_json_ld.html", takes_context=True)
def category_json_ld(context, category, products=None, subcategories=None):
    """Render CollectionPage JSON-LD.
    Usage:
      {% category_json_ld category products %}
      {% category_json_ld category subcategories=subcategories %}
    """
    request = context["request"]
    items = []
    if subcategories is not None:
        for position, subcategory in enumerate(subcategories, start=1):
            items.append(
                {
                    "@type": "ListItem",
                    "position": position,
                    "name": subcategory.name_ar,
                    "url": _absolute_uri(
                        request, reverse("product-type", args=[subcategory.slug])
                    ),
                }
            )
    else:
        if products is None:
            products = category.products.filter(is_active=True)[:20]
        for position, product in enumerate(products, start=1):
            items.append(
                {
                    "@type": "ListItem",
                    "position": position,
                    "name": product.name_ar,
                    "url": _absolute_uri(
                        request, reverse("product-detail", args=[product.pk])
                    ),
                }
            )
    data = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"{category.name_ar} | درة تريم",
        "url": _absolute_uri(request, reverse("product-type", args=[category.slug])),
        "mainEntity": {"@type": "ItemList", "itemListElement": items},
    }
    return {"json_ld": _json_ld(data)}


@register.inclusion_tag("catalog/partials/breadcrumb_json_ld.html", takes_context=True)
def breadcrumb_json_ld(context, items):
    """Render BreadcrumbList JSON-LD from a list of (name, url) pairs.
    Usage: {% breadcrumb_json_ld breadcrumbs %}"""
    request = context["request"]
    elements = []
    for position, (name, url) in enumerate(items, start=1):
        if url and not url.startswith("http"):
            url = _absolute_uri(request, url)
        elements.append(
            {
                "@type": "ListItem",
                "position": position,
                "name": name,
                "item": url,
            }
        )
    return {
        "json_ld": _json_ld(
            {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": elements,
            }
        )
    }
