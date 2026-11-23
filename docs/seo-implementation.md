# SEO Implementation

**Project:** Durrat Tarim Django (درة تريم)
**Branch documented:** `dev/integration` (commit `5461a3c`)
**Date:** 2026-11-22
**Scope:** SEO work delivered by agents A1 (meta tags), A2 (structured data), and A3 (sitemaps + robots.txt), consolidated for A4.

---

## 1. Summary

The SEO overhaul adds four layers to the storefront:

1. **Head metadata** — dynamic title/description, canonical URLs, Open Graph, Twitter Cards, robots meta, Google verification, and dynamic `theme-color`.
2. **Site-wide structured data** — `Organization` and `WebSite` (with `SearchAction`) JSON-LD in the shared head partial.
3. **Per-page structured data** — `Product`, `CollectionPage`, and `BreadcrumbList` JSON-LD emitted through a single safe serializer.
4. **Crawl discovery** — a request-host-aware sitemap index with per-section sitemaps, plus a hardened `robots.txt`.

All absolute URLs are derived from the **incoming request host**, not from `django.contrib.sites`, so the same code works on localhost, Vercel previews, and a future production domain without changing `SITE_ID` or `Site.domain`.

---

## 2. Branch-by-branch work

| Agent | Branch | Key files | What it delivered |
|-------|--------|-----------|-------------------|
| **A1** | `dev/seo-meta-tags` | `templates/partials/head.html` | Canonical URL, OG/Twitter tags, `Organization` JSON-LD, `WebSite` + `SearchAction` JSON-LD, dynamic `theme-color`, robots meta, Google site verification. |
| **A2** | `dev/seo-structured-data` | `catalog/templatetags/catalog_tags.py`, `catalog/models.py`, `catalog/views.py`, five storefront templates, three JSON-LD partials | `Product` / `CollectionPage` / `BreadcrumbList` JSON-LD, reusable `_json_ld` serializer, `get_absolute_url()` on models, breadcrumb context, `robots_content` on search. |
| **A3** | `dev/seo-sitemap` | `catalog/sitemaps.py`, `durrat_tarim/sitemap_views.py`, `durrat_tarim/urls.py` | `StaticViewSitemap` / `CategorySitemap` / `ProductSitemap` with `lastmod`, request-aware sitemap views (`RequestSite`), sitemap routes, and `robots.txt` rules. |
| **A4** | `dev/seo-docs` | `docs/seo-implementation.md` (this file) | Consolidates and documents the work above. |

Related theme work (not part of A1–A3) moved the inline CSS custom properties out of `head.html` into `templates/partials/theme-variables.html`; `theme-color` is driven by the same `StoreSettings` color fields.

---

## 3. A1 — Head metadata (`templates/partials/head.html`)

`templates/base.html` includes `partials/head.html` at the top of `<head>`, so every page inherits the tags below. Pages can add more via `{% block extra_head %}`.

### 3.1 Template context variables

Views pass these variables to override defaults. All are optional.

| Variable | Used by | Purpose / fallback |
|----------|---------|--------------------|
| `page_title` | `<title>`, `og:title`, `twitter:title` | Defaults to `درة تريم للأقمشة`. |
| `meta_description` | `<meta name="description">`, OG/Twitter description | Defaults to `تصفحي أحدث الأزياء`; truncated to 160 characters. |
| `og_type` | `og:type` | Defaults to `website`; product pages set `product`. |
| `og_image` | `og:image`, `twitter:image` | Defaults to the site logo (`static/images/logo-gold-transparent.png`), made absolute with the request scheme/host. |
| `robots_content` | `<meta name="robots">` | Defaults to `index,follow`; search sets `noindex,follow`. |
| `product` | `<title>` suffix | When present, appends the product name. |
| `category` | `<title>` suffix | When present, appends the category name. |
| `site_settings` | `theme-color`, `Organization` phone | Injected globally by the store context processor. |

### 3.2 Title and description

```django
<title>
    {{ page_title|default:"درة تريم للأقمشة" }}
    {% if product %} - {{ product.name_ar }}{% endif %}
    {% if category %} - {{ category.name_ar }}{% endif %}
    - درة تريم
</title>
```

The description default and every view-supplied description are truncated with `truncatechars:160`.

### 3.3 Canonical URL

```django
<link rel="canonical"
      href="{{ request.scheme }}://{{ request.get_host }}{{ request.path }}{% if request.GET %}?page=1{% endif %}" />
```

- Uses the request scheme and host, so it follows the domain the page is actually served from.
- Strips all query parameters.
- Any URL with a query string canonicalizes to `?page=1`. This intentionally collapses filter/search/pagination variants onto the primary page, but it also means `?page=2` canonicalizes to `?page=1` (see §8.4).

### 3.4 Open Graph and Twitter Cards

Open Graph tags: `og:type`, `og:url`, `og:site_name` (`درة تريم`), `og:locale` (`ar_AR`), `og:title`, `og:description`, `og:image`.
Twitter tags use `summary_large_image` with title, description, and image.

`og:url` is built as `request.scheme://request.get_host + request.path` and deliberately omits the query string.

### 3.5 Site-wide JSON-LD

**Organization** (`@type: Organization`) is emitted on every page with:

- `name`: `درة تريم`
- `url` and `logo`: absolute request-host URLs
- `contactPoint`: telephone from `site_settings.whatsapp_number` (fallback `967783278181`), `contactType: customer service`, `areaServed: YE`
- `sameAs`: Instagram, Snapchat, TikTok profile URLs

**WebSite** (`@type: WebSite`) is emitted on every page with a `SearchAction` targeting the existing `product-search` URL:

```json
{
  "@type": "SearchAction",
  "target": {
    "@type": "EntryPoint",
    "urlTemplate": "https://<host>/products/search/?q={search_term_string}"
  },
  "query-input": "required name=search_term_string"
}
```

The actual URL comes from `{% url 'product-search' %}`, so it stays correct if routes change.

### 3.6 Dynamic theme-color

```django
{% if site_settings %}
<meta name="theme-color" content="{{ site_settings.light_color_background }}" media="(prefers-color-scheme: light)" />
<meta name="theme-color" content="{{ site_settings.dark_color_background }}" media="(prefers-color-scheme: dark)" />
{% else %}
<meta name="theme-color" content="#f6f1ee" media="(prefers-color-scheme: light)" />
<meta name="theme-color" content="#08121b" media="(prefers-color-scheme: dark)" />
{% endif %}
```

This resolves the A1/B cross-task coordination point: the value is no longer hardcoded when `StoreSettings` exists, and keeps safe defaults when it does not. It uses the same fields that feed `--color-background` in `theme-variables.html`.

### 3.7 Robots, verification, and future hreflang

- `<meta name="robots" content="{{ robots_content|default:'index,follow' }}">`
- Google Search Console verification meta tag is hardcoded in the partial (`google-site-verification`).
- A commented `hreflang` placeholder remains for future multilingual support.

---

## 4. A2 — Structured data

### 4.1 The single serializer: `catalog_tags._json_ld`

All per-page structured data goes through one helper in `catalog/templatetags/catalog_tags.py`:

```python
def _json_ld(data):
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    return mark_safe(payload.replace("</", "<\\/"))
```

Why this shape:

- `ensure_ascii=False` keeps Arabic text readable in the output.
- `indent=2` makes the JSON-LD reviewable in page source.
- `.replace("</", "<\\/")` prevents any string value (product/category names, descriptions) from closing the surrounding `<script>` tag early. This is the key XSS/injection defense for embedded JSON.
- `mark_safe` stops Django autoescaping the JSON, which would turn quotes into `&quot;` and produce invalid JSON-LD.

Every inclusion tag returns `{"json_ld": _json_ld(data)}`; the matching partial prints it inside `<script type="application/ld+json">` with no further escaping.

### 4.2 Template tags and partials

| Tag | Partial | Output |
|-----|---------|--------|
| `{% product_json_ld product %}` | `templates/catalog/partials/product_json_ld.html` | `Product` |
| `{% category_json_ld category products %}` | `templates/catalog/partials/category_json_ld.html` | `CollectionPage` + `ItemList` |
| `{% breadcrumb_json_ld breadcrumbs %}` | `templates/catalog/partials/breadcrumb_json_ld.html` | `BreadcrumbList` |

All three are inclusion tags with `takes_context=True`, so they can call `request.build_absolute_uri()` for absolute URLs.

### 4.3 Product JSON-LD

Emitted on product detail pages:

| Field | Value |
|-------|-------|
| `@type` | `Product` |
| `name` | `product.name_ar` |
| `description` | `product.description_ar` or the product name, capped at 5000 chars |
| `sku` | `product.slug` |
| `url` | Absolute `product-detail` URL (keyed by pk) |
| `brand` | `Brand` named `درّة تريم` |
| `offers` | `Offer` with `price` (`price_sar` as string), `priceCurrency: SAR`, `availability: InStock`, `itemCondition: NewCondition`, and the same URL |
| `category` | Category name, when the product has one |
| `image` | Absolute image URL list, when an image exists |

Notes:
- Prices are advertised in SAR only; the YER conversion shown in the UI is not part of the structured data.
- `availability` is always `InStock` because the catalog has no stock/inventory field.
- No `aggregateRating` is emitted because the project has no review/rating model.

### 4.4 CollectionPage JSON-LD

Emitted on category/type pages:

- `@type: CollectionPage`
- `name`: `"<category> | درة تريم"`
- `url`: absolute `product-type` URL
- `mainEntity`: `ItemList` whose `itemListElement` entries are `ListItem` records with `position`, `name`, and absolute product URL

The view passes the current page's products (`page_obj.object_list`). If the tag is called without a product list it falls back to the first 20 active products in the category. Only the products actually rendered on the page are included, which keeps structured data consistent with visible content.

### 4.5 BreadcrumbList JSON-LD

Every storefront page that sets `breadcrumbs` emits a `BreadcrumbList`:

```python
"breadcrumbs": [
    ("الرئيسية", "/"),
    ("التصنيفات", reverse("product-types")),
    (category.name_ar, reverse("product-type", args=[category.slug])),
    (product.name_ar, product.get_absolute_url()),
]
```

- Items are `(name, url)` tuples.
- Relative URLs are converted to absolute with `request.build_absolute_uri()`; already-absolute URLs are left alone.
- Each item becomes `{"@type": "ListItem", "position": N, "name": ..., "item": ...}`.

The final crumb may point at the current page URL. That is valid and keeps the trail complete.

### 4.6 Models and views changes

`catalog/models.py`:

- `Category.get_absolute_url()` → `reverse("product-type", args=[self.slug])`
- `Product.get_absolute_url()` → `reverse("product-detail", args=[self.pk])` (detail routes are pk-based, not slug-based)
- The 10 `StoreSettings` color fields gained `help_text` values naming their **design tokens** (`--color-primary`, `--color-background`, etc.). This links the admin UI to the theme system and is harmless to SEO code.

`catalog/views.py`:

- `search_products`: adds `robots_content = "noindex,follow"` and its breadcrumb trail.
- `get_all_types`, `get_type_products`, `product_details`: add breadcrumb trails.
- `product_details`: keeps `og_type = "product"` and `og_image` for share previews.

### 4.7 Where the tags are included

| Template | Structured data |
|----------|-----------------|
| `templates/index.html` | Site-wide `Organization` + `WebSite` only (from head partial) |
| `templates/types.html` | `BreadcrumbList` |
| `templates/type_products.html` | `CollectionPage` + `BreadcrumbList` |
| `templates/product_details.html` | `Product` + `BreadcrumbList` |
| `templates/search.html` | `BreadcrumbList` (plus `noindex,follow`) |

Each template starts with `{% load catalog_tags %}` and renders the tags at the top of `{% block content %}`.

---

## 5. A3 — Sitemaps and robots.txt

### 5.1 Sitemap classes (`catalog/sitemaps.py`)

| Class | Section key | Items | `changefreq` | `priority` | `lastmod` |
|-------|-------------|-------|--------------|------------|-----------|
| `StaticViewSitemap` | `static` | `home`, `product-types`, `contact` | weekly | 1.0 / 0.8 / 0.4 | Latest `StoreSettings.updated_at`, or omitted if no settings row |
| `CategorySitemap` | `categories` | Active `Category` rows, ordered by pk | weekly | 0.7 | `category.updated_at` |
| `ProductSitemap` | `products` | Active products in active categories, ordered by pk | daily | 0.9 | `product.updated_at` |

Search pages are intentionally excluded from `StaticViewSitemap`; they are also `noindex`.

### 5.2 Routes (`durrat_tarim/urls.py`)

| URL | View | Purpose |
|-----|------|---------|
| `/sitemap.xml` | `sitemap_views.index` | Sitemap index listing all sections |
| `/sitemap-static.xml` | `sitemap_views.sitemap` | Static-page URL set |
| `/sitemap-categories.xml` | `sitemap_views.sitemap` | Category URL set |
| `/sitemap-products.xml` | `sitemap_views.sitemap` | Product URL set |
| `/robots.txt` | `robots_txt` | Crawl directives + sitemap pointer |

When a section has multiple pages, the index includes `?p=2`, `?p=3`, … entries for it.

The view names deliberately reuse `django.contrib.sitemaps.views.index` / `.sitemap`, so `reverse()` and existing code that expects those names continue to work while the custom implementations run.

### 5.3 Absolute URLs: request host, not `django.contrib.sites`

`durrat_tarim/sitemap_views.py` is a request-aware replacement for Django's stock sitemap views. The stock views resolve absolute URLs through `django.contrib.sites` (`SITE_ID` → `Site.domain`), which in this project is still the default `example.com`. Using them would publish a sitemap pointing at the wrong domain.

The wrappers instead build a `RequestSite(request)` and pass it to `get_urls(page=..., site=site, protocol=request.scheme)`. Consequences:

- The sitemap always matches the domain the request arrived on (localhost, Vercel preview, production).
- `https` is preserved when the request reaches Django over HTTPS (Vercel sets `SECURE_PROXY_SSL_HEADER` and `USE_X_FORWARDED_HOST` when `VERCEL` is set).
- No `Site` row needs to be edited or migrated per environment.
- `robots.txt` uses `request.build_absolute_uri(reverse("django.contrib.sitemaps.views.index"))`, so its `Sitemap:` line follows the same host.

### 5.4 `lastmod` handling

- `StaticViewSitemap.lastmod` returns the newest `StoreSettings.updated_at`, or `None` when no settings row exists (Django omits the tag rather than inventing a date).
- Category and product sitemaps return their model's `updated_at`.
- Both custom views add a `Last-Modified` response header when **every** section/item exposes a last modification time. `_latest_lastmod` normalizes dates/datetimes and makes naive values timezone-aware.
- The sitemap responses also send `X-Robots-Tag: noindex, noodp, noarchive`. This is standard for XML sitemaps: crawlers may fetch them, but they should not appear as search results.

### 5.5 robots.txt rules

The view returns `text/plain`:

```text
User-agent: *
Allow: /
Disallow: /admin/
Disallow: /auth/
Disallow: /dashboard/
Disallow: /favorites/
Disallow: /search/
Disallow: /*?*

Sitemap: <absolute URL of /sitemap.xml>
```

Rationale:

- Storefront pages remain crawlable via `Allow: /`.
- Admin, auth, dashboard, favorites, and search are private/app areas and are excluded.
- `Disallow: /*?*` blocks arbitrary query-string URLs (filters, search parameters, tracking variants).
- The sitemap line is absolute and host-aware.

---

## 6. How to extend the SEO work

### 6.1 Add JSON-LD to a new page type

1. Build the data dict in `catalog/templatetags/catalog_tags.py`, using `context["request"]` and `request.build_absolute_uri()` for URLs.
2. Return `{"json_ld": _json_ld(data)}` from an inclusion tag.
3. Add a partial under `templates/catalog/partials/` that prints `{{ json_ld }}` inside `<script type="application/ld+json">`.
4. In the page template, `{% load catalog_tags %}` and call the tag inside the content block.
5. Validate with Google's Rich Results Test and the Schema.org validator.

Never call `json.dumps` directly in a template tag for embedded output; use `_json_ld` so `</` escaping and `mark_safe` stay consistent.

### 6.2 Add a new sitemap section

1. Subclass `django.contrib.sitemaps.Sitemap` in `catalog/sitemaps.py` and implement `items()` and `location()`; add `lastmod()` if a reliable timestamp exists.
2. Register it in the `sitemaps` dict in `durrat_tarim/urls.py`.
3. It is then served automatically at `/sitemap-<section>.xml` and listed in `/sitemap.xml`.

### 6.3 Add a static page to the sitemap

Append a `(url_name, priority)` tuple to `StaticViewSitemap.items()`. Add `lastmod` support if the page is data-driven.

### 6.4 Add per-page metadata

Set `page_title`, `meta_description`, `robots_content`, `og_type`, and `og_image` in the view context. The head partial picks them up automatically. Set `breadcrumbs` when the page has a hierarchy.

---

## 7. Validation and testing

Useful checks after deployment or when changing SEO code:

```bash
# Django checks and full suite
python manage.py check
python manage.py test

# Inspect metadata and structured data in rendered HTML
python manage.py runserver
# then open page source and look for canonical, og:*, twitter:*, application/ld+json

# Sitemap and robots endpoints
curl -s http://127.0.0.1:8000/robots.txt
curl -s http://127.0.0.1:8000/sitemap.xml
curl -s http://127.0.0.1:8000/sitemap-static.xml
curl -s http://127.0.0.1:8000/sitemap-categories.xml
curl -s http://127.0.0.1:8000/sitemap-products.xml

# XML well-formedness
curl -s http://127.0.0.1:8000/sitemap.xml | python -c "import sys, xml.dom.minidom; xml.dom.minidom.parseString(sys.stdin.read()); print('valid XML')"
```

Regression coverage from the existing suite: 52 tests pass on `dev/integration`, and `npm run build` succeeds. There are currently no dedicated assertions for sitemap/JSON-LD output; the SEO endpoints are best verified with the commands above and Google's tools.

External validators:

- Google Rich Results Test — Product, Breadcrumb, Organization
- Schema Markup Validator — raw JSON-LD
- Google Search Console — submit `/sitemap.xml`, inspect robots.txt, request indexing

---

## 8. Production considerations

### 8.1 Production domain is not finalized

The SEO code is deliberately host-relative, but the hosting configuration is not yet production-complete:

- `ALLOWED_HOSTS = [".vercel.app", "127.0.0.1", "localhost"]` — a custom production domain must be added before it can serve requests.
- `CSRF_TRUSTED_ORIGINS` already lists `https://durrat-tarim.com` and `https://www.durrat-tarim.com`, which suggests the intended domain, but this is not reflected in `ALLOWED_HOSTS`.
- Until the domain is fixed, canonical/sitemap/robots URLs will follow whatever host the request used (preview URL vs. custom domain). Make sure Search Console is pointed at the final host and that preview deployments are not indexed.

`django.contrib.sites` / `SITE_ID` are intentionally **not** used for sitemap absolute URLs, so no `Site` row update is required when the domain changes.

### 8.2 Database: SQLite locally, PostgreSQL/Supabase remotely

`durrat_tarim/settings.py` chooses the database at startup:

- `USE_REMOTE_DB=True` plus `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, and `POSTGRES_DB` → PostgreSQL (Supabase-style remote database, `CONN_MAX_AGE=300`, health checks, keepalives).
- Otherwise → local `db.sqlite3`.

Sitemap `lastmod` values come from `updated_at` and `StoreSettings.updated_at`; those columns exist in both backends. Be aware that the local SQLite file (`db.sqlite3`) is not the production data source, so sitemap contents and lastmod dates on a local run will not match production.

### 8.3 HTTPS and proxy headers

Absolute URLs use `request.scheme`. On Vercel, `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` and `USE_X_FORWARDED_HOST = True` are enabled only when the `VERCEL` environment variable is set. If you deploy behind a different proxy, configure the equivalent headers, otherwise canonical/sitemap URLs may be emitted as `http://`.

When `DEBUG=False`, the project also enables secure cookies, `SECURE_SSL_REDIRECT`, and HSTS. Crawlers should always see the HTTPS canonical form.

### 8.4 Known limitations / follow-ups

- **Title duplication:** views already put the product/category name in `page_title` (for example `"<name> | درة تريم"`), and the head partial also appends `product.name_ar` / `category.name_ar`, producing a repeated name in `<title>`. Consider removing one of the two suffixes.
- **Pagination canonical:** any query string canonicalizes to `?page=1`, including `?page=2`. This consolidates variants but is not ideal for deep pagination; consider preserving `page` while dropping other parameters.
- **`robots.txt` vs. meta robots:** `/search/` is disallowed in `robots.txt` and the search view sets `noindex,follow`, but auth pages rely on the `robots.txt` disallow only (their meta robots remains the default `index,follow`). Add `robots_content = "noindex,follow"` to auth/dashboard views if defense in depth is wanted.
- **No review/rating data:** Product JSON-LD has no `aggregateRating`. Add it only when a real review model exists.
- **Always in stock:** Product offers always declare `InStock` because inventory is not tracked.
- **SAR-only pricing:** structured data exposes the SAR price only, not the displayed YER conversion.
- **Hardcoded verification token:** the Google Search Console token lives directly in `head.html`; consider moving it to an environment setting if multiple environments need different properties.
- **Sitemap scope:** sitemaps include active products/categories and three static pages only; dashboard, auth, favorites, and search are intentionally absent.

---

## 9. File reference

| Path | Role |
|------|------|
| `templates/partials/head.html` | All head metadata and site-wide JSON-LD |
| `templates/partials/theme-variables.html` | Theme CSS variables used by `theme-color` |
| `templates/catalog/partials/product_json_ld.html` | Product JSON-LD script wrapper |
| `templates/catalog/partials/category_json_ld.html` | CollectionPage JSON-LD script wrapper |
| `templates/catalog/partials/breadcrumb_json_ld.html` | BreadcrumbList JSON-LD script wrapper |
| `catalog/templatetags/catalog_tags.py` | `_json_ld` serializer and inclusion tags |
| `catalog/models.py` | `get_absolute_url()` methods; color-token `help_text` |
| `catalog/views.py` | Page metadata, breadcrumbs, `robots_content` |
| `catalog/sitemaps.py` | Sitemap classes and `lastmod` |
| `durrat_tarim/sitemap_views.py` | Request-aware sitemap index/section views |
| `durrat_tarim/urls.py` | Sitemap routes and `robots.txt` |
| `durrat_tarim/settings.py` | Hosts, proxy headers, database selection |
| `docs/recon.md` / `docs/master-plan.md` | Original audit and plan for this work |
