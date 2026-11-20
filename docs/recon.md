# Recon: Durrat Tarim Django + Tailwind v4 Codebase

**Date:** 2026-11-20  
**Branch:** main  
**Commit:** 20a2f66

---

## 1. Project Overview

A Django 4.x e-commerce storefront for Arabic fabrics with:
- **Auth:** django-allauth (email + Google OAuth)
- **Styling:** Tailwind v4 (CSS-first `@theme` syntax, `@source` content detection)
- **Media:** ImageKit (with local FileSystemStorage fallback)
- **Static:** Whitenoise (CompressedStaticFilesStorage)
- **DB:** SQLite (local) / PostgreSQL (remote via env)
- **Deploy:** Vercel-ready (SECURE_PROXY_SSL_HEADER, env-driven config)
- **Language:** Arabic RTL (`dir="rtl"`, `lang="ar"`)

---

## 2. Current Theme System (10 CSS Custom Properties)

### 2.1 StoreSettings Model (`catalog/models.py`)

```python
class StoreSettings(models.Model):
    # Light theme (5 fields)
    light_color_primary     = CharField(max_length=7, default="#30669c")
    light_color_secondary   = CharField(max_length=7, default="#08121b")
    light_color_accent      = CharField(max_length=7, default="#e0801f")
    light_color_background  = CharField(max_length=7, default="#f6f1ee")
    light_color_surface     = CharField(max_length=7, default="#ffffff")
    
    # Dark theme (5 fields)
    dark_color_primary      = CharField(max_length=7, default="#39f2f9")
    dark_color_secondary    = CharField(max_length=7, default="#e0ebe7")
    dark_color_accent       = CharField(max_length=7, default="#e7994b")
    dark_color_background   = CharField(max_length=7, default="#08121b")
    dark_color_surface      = CharField(max_length=7, default="#0c1927")
    
    # Validator: _validate_hex_color (enforces #RRGGBB format)
```

**Singleton pattern:** `save()` forces `pk=1`, `load()` gets or creates `pk=1`.

### 2.2 Admin (`catalog/admin.py`)

```python
class StoreSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Light Theme Colors", fields=('light_color_primary', 'light_color_secondary', 
                                       'light_color_accent', 'light_color_background', 'light_color_surface')),
        ("Dark Theme Colors", fields=('dark_color_primary', 'dark_color_secondary',
                                      'dark_color_accent', 'dark_color_background', 'dark_color_surface')),
    )
    def has_add_permission(self, request): 
        return not StoreSettings.objects.exists()
```

### 2.3 Template Injection (`templates/partials/head.html:92-115`)

```html
{% if site_settings %}
<style>
    :root {
        --color-primary: {{ site_settings.light_color_primary|default:"#30669c" }};
        --color-secondary: {{ site_settings.light_color_secondary|default:"#08121b" }};
        --color-accent: {{ site_settings.light_color_accent|default:"#e0801f" }};
        --color-background: {{ site_settings.light_color_background|default:"#f6f1ee" }};
        --color-surface: {{ site_settings.light_color_surface|default:"#ffffff" }};
    }
    html.dark {
        --color-primary: {{ site_settings.dark_color_primary|default:"#39f2f9" }};
        --color-secondary: {{ site_settings.dark_color_secondary|default:"#e0ebe7" }};
        --color-accent: {{ site_settings.dark_color_accent|default:"#e7994b" }};
        --color-background: {{ site_settings.dark_color_background|default:"#08121b" }};
        --color-surface: {{ site_settings.dark_color_surface|default:"#0c1927" }};
    }
    body { background-color: var(--color-background); color: var(--color-secondary); }
</style>
{% endif %}
```

### 2.4 Tailwind v4 Config (`static/css/input.css`)

```css
@import "tailwindcss";

@theme {
    /* Only 6 tokens defined — missing: surface, secondary */
    --color-primary: #30669c;
    --color-accent: #e0801f;
    --color-background: #f6f1ee;
    --color-text: #08121b;
    --color-border: #e5e5e5;
    --color-focus: #e0801f;
    
    /* Rose palette (10 shades) */
    --color-rose-50: #fff1f2; ... --color-rose-950: #4c0519;
    
    /* Fonts */
    --font-tajawal: "Tajawal", "sans-serif";
    --font-cairo: "Cairo", "sans-serif";
    --font-el-messiri: "El Messiri", "sans-serif";
}

@source "../templates/**/*.html";
@source "../static/js/**/*.js";
```

**Gap:** Tailwind tokens don't match all 10 CSS custom properties (missing `--color-surface`, `--color-secondary` in `@theme`).

### 2.5 Theme Toggle (`static/js/theme.js`)

- Toggles `html.dark` class
- Persists to `localStorage`
- Respects `prefers-color-scheme` on first visit

---

## 3. Current SEO State

### 3.1 Implemented (`templates/partials/head.html`)

| Feature | Status | Notes |
|---------|--------|-------|
| `<title>` | ✅ | Dynamic via `page_title` |
| `meta description` | ✅ | Dynamic via `meta_description` |
| Canonical URL | ✅ | `request.scheme://host/path` |
| Open Graph (og:*) | ✅ | type, url, site_name, locale, title, description, image |
| Twitter Card | ✅ | summary_large_image + title, description, image |
| JSON-LD Organization | ✅ | Site-wide, includes logo, contact, social links |
| Google Site Verification | ✅ | Hardcoded meta tag |
| `theme-color` | ⚠️ | **Hardcoded** `#f6f1ee` (line 80) — should use theme token |

### 3.2 Missing

| Feature | Required By | Notes |
|---------|-------------|-------|
| Sitemap (`/sitemap.xml`) | Google Search Console | `catalog/sitemaps.py` exists but **not wired in `urls.py`** |
| `robots.txt` | All crawlers | Not present |
| Product JSON-LD | Rich snippets (price, availability, review) | Only Organization exists |
| Category JSON-LD | Collection rich results | Missing |
| Breadcrumb JSON-LD | Site structure | Missing |

### 3.3 Sitemaps (`catalog/sitemaps.py`)

Three sections defined but **not mounted**:
1. `StaticViewSitemap` — home, product-types, contact (weekly, priorities 1.0/0.8/0.4)
2. `CategorySitemap` — active categories (weekly, 0.7)
3. `ProductSitemap` — active products in active categories (daily, 0.9)

---

## 4. Key Files Inventory

| File | Purpose |
|------|---------|
| `templates/base.html` | Main layout, includes head/header/footer, loads theme.js + animations.js |
| `templates/partials/head.html` | All SEO meta tags, JSON-LD Organization, inline CSS custom properties |
| `templates/partials/header.html` | Navigation, theme toggle (desktop + mobile), search, auth links |
| `catalog/models.py` | StoreSettings (10 color fields + validator), Category, Product |
| `catalog/admin.py` | StoreSettingsAdmin with 2 fieldsets (light/dark) |
| `catalog/sitemaps.py` | 3 sitemap classes (not yet in urls.py) |
| `catalog/context_processors.py` | `site_context` → injects `site_settings` into all templates |
| `static/css/input.css` | Tailwind v4 `@theme` (6 tokens + rose palette + fonts) |
| `static/css/output.css` | Built output (gitignored) |
| `static/js/theme.js` | Dark mode toggle + localStorage persistence |
| `static/js/animations.js` | Scroll animations |
| `durrat_tarim/settings.py` | Django config (sitemaps in INSTALLED_APPS, site_context processor) |
| `durrat_tarim/urls.py` | URL routing (sitemap not yet included) |
| `package.json` | Tailwind v4 build script |

---

## 5. Identified Gaps & TODOs

### Theme System (Task B)
1. **Token mismatch:** Tailwind `@theme` has 6 tokens; CSS custom properties has 10
2. **Hardcoded theme-color:** Line 80 in `head.html` uses `#f6f1ee` instead of CSS variable
3. **Admin fields:** Only 10 color fields — no font, spacing, border-radius tokens
4. **No design tokens file:** Tokens scattered across model, admin, template, CSS
5. **Missing tests:** No test coverage for theme system

### SEO (Task A)
1. **Sitemap not wired:** `urls.py` missing sitemap view
2. **No robots.txt:** Need static file or view
3. **No Product/Category JSON-LD:** Only Organization exists
4. **Hardcoded theme-color:** Same as above
5. **No SEO documentation:** No `docs/seo-checklist.md`

---

## 6. Branch Strategy for Multi-Agent Work

| Agent | Task | Branch Name | Depends On |
|-------|------|-------------|------------|
| A1 | Meta tags (title, description, OG, Twitter, canonical) | `dev/seo-meta-tags` | — |
| A2 | Structured data (Product, Category, Breadcrumb JSON-LD) | `dev/seo-structured-data` | — |
| A3 | Sitemap + robots.txt | `dev/seo-sitemap` | — |
| A4 | SEO documentation | `dev/seo-docs` | A1, A2, A3 |
| B1 | Theme audit → token inventory + theme-plan.md | `dev/theme-audit` | — (MUST RUN FIRST) |
| B2 | StoreSettingsAdmin updates (new fields per B1 plan) | `dev/theme-admin` | B1 (plan) |
| B3 | Template refactor (inline styles → Tailwind tokens) | `dev/theme-templates` | B1 (tokens finalized) |
| B4 | Static files (input.css @theme expansion) | `dev/theme-static` | B1 (tokens finalized) |
| B5 | Theme tests | `dev/theme-tests` | B3, B4 |

---

## 7. Cross-Task Coordination Point

**`theme-color` meta tag** (head.html:80):
- Currently hardcoded: `content="#f6f1ee"`
- **If Task A lands first:** Use `TODO(theme)` placeholder → `content="#TODO(theme)"` with comment
- **If Task B lands first:** Use `var(--color-background)` via inline style or CSS variable
- **Resolution:** Final merge must use dynamic theme token

---

## 8. Next Steps

1. ✅ Recon complete — this document
2. 📋 Create master plan (checklist with sub-agent assignments, branch names, dependencies)
3. 🔀 Create dev branch (if not exists) and push to origin
4. 🚀 Spawn agents per sequencing rules:
   - **Wave 1:** B1 (audit→plan) + A1-A4 (can run in parallel)
   - **Wave 2:** After B1 completes → B2 (admin), B3 (templates), B4 (static) in parallel
   - **Wave 3:** After B3+B4 complete → B5 (tests)
5. 🔍 Review each PR against repo standards
6. 📊 Final integration report