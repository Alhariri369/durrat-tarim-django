import json

from django import template
from django.templatetags.static import static
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
        "brand": {"@type": "Brand", "name": "درة تريم"},
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


@register.inclusion_tag("catalog/partials/category_json_ld.html", takes_context=True)
def catalog_json_ld(context, name, url_path, products):
    """Render CollectionPage JSON-LD for a general catalog listing (/products/)."""
    request = context["request"]
    items = [
        {
            "@type": "ListItem",
            "position": position,
            "name": product.name_ar,
            "url": _absolute_uri(
                request, reverse("product-detail", args=[product.pk])
            ),
        }
        for position, product in enumerate(products, start=1)
    ]
    data = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"{name} | درة تريم",
        "url": _absolute_uri(request, url_path),
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


@register.inclusion_tag("catalog/partials/store_json_ld.html", takes_context=True)
def store_json_ld(context):
    """Render site-wide ClothingStore (local SEO) and WebSite (SearchAction) JSON-LD."""
    request = context["request"]
    site_settings = context.get("site_settings")
    base_url = f"{request.scheme}://{request.get_host()}"
    logo_url = _absolute_uri(request, static("images/logo-gold-transparent.png"))
    og_image_url = context.get("default_og_image_url") or _absolute_uri(
        request, static("images/og-default.jpg")
    )
    whatsapp = (
        getattr(site_settings, "whatsapp_number", "") or "967783278181"
    ).lstrip("+")
    address_ar = getattr(site_settings, "address_ar", "") or "سوق الفتح"

    store_data = {
        "@context": "https://schema.org",
        "@type": "ClothingStore",
        "name": "درة تريم",
        "description": "متجر درة تريم للقطع العرائسية والأقمشة والأزياء الراقية في تريم وسيئون ووادي حضرموت واليمن.",
        "url": base_url,
        "logo": logo_url,
        "image": og_image_url,
        "telephone": f"+{whatsapp}",
        "priceRange": "$$",
        "currenciesAccepted": "SAR, YER",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": address_ar,
            "addressLocality": "تريم",
            "addressRegion": "حضرموت",
            "addressCountry": "YE",
        },
        "geo": {
            "@type": "GeoCoordinates",
            "latitude": 16.05294,
            "longitude": 48.97709,
        },
        "areaServed": [
            {"@type": "City", "name": "تريم"},
            {"@type": "City", "name": "سيئون"},
            {"@type": "AdministrativeArea", "name": "وادي حضرموت"},
            {"@type": "Country", "name": "اليمن"},
        ],
        "openingHoursSpecification": [
            {
                "@type": "OpeningHoursSpecification",
                "dayOfWeek": [
                    "Saturday",
                    "Sunday",
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                ],
                "opens": "09:00",
                "closes": "21:30",
            },
            {
                "@type": "OpeningHoursSpecification",
                "dayOfWeek": ["Friday"],
                "opens": "16:00",
                "closes": "22:00",
            },
        ],
        "contactPoint": {
            "@type": "ContactPoint",
            "telephone": f"+{whatsapp}",
            "contactType": "customer service",
            "areaServed": "YE",
            "availableLanguage": ["Arabic"],
        },
        "sameAs": [
            "https://www.instagram.com/durttrim/",
            "https://www.snapchat.com/add/durttrim",
            "https://www.tiktok.com/@durttrim",
        ],
    }

    website_data = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "url": base_url,
        "name": "درة تريم",
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": f"{base_url}{reverse('product-search')}?q={{search_term_string}}",
            },
            "query-input": "required name=search_term_string",
        },
    }

    return {
        "store_json_ld": _json_ld(store_data),
        "website_json_ld": _json_ld(website_data),
    }


@register.inclusion_tag("catalog/partials/faq_json_ld.html")
def faq_json_ld(faqs):
    """Render FAQPage JSON-LD from a list of {'question', 'answer'} dicts."""
    if not faqs:
        return {"json_ld": ""}
    data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": item["answer"],
                },
            }
            for item in faqs
        ],
    }
    return {"json_ld": _json_ld(data)}
