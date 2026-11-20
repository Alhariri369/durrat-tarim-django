# درة تريم (Durrat Tarim) — Django E-commerce Storefront

A modern, Arabic-first Django e-commerce application for a Saudi/Yemeni fashion boutique. Built with **Django 5.x**, **django-allauth**, **Tailwind CSS**, **ImageKit** for media, and **Vercel** deployment in mind.

---

## 🎯 Project Overview

**Durrat Tarim** is a bilingual (Arabic/English) RTL-enabled storefront where customers browse abayas, dresses, and accessories, inquire via WhatsApp, and save favorites. It uses **WhatsApp as the primary checkout/inquiry channel** — no payment gateway integration, just direct WhatsApp conversations.

### Key Features

| Area | Highlights |
|------|------------|
| **Authentication** | Email/password + Google OAuth via `django-allauth`; custom User model (UUID PK, email as username, no username field); mandatory email verification; rate-limited login |
| **Catalog** | Categories, products with multiple images, SAR/YER dual-currency display (admin-configurable rate), Arabic text normalization for search |
| **Favorites** | Authenticated + email-verified users only; heart-toggle on product cards; bulk WhatsApp share of selected favorites |
| **WhatsApp Integration** | Pre-filled product inquiry messages; favorites collection sharing; click tracking via Django signals |
| **Store Settings** | Singleton `StoreSettings` model: WhatsApp number, currency rate, light/dark theme colors, SEO fields — all editable in Django admin |
| **Contact/Support** | Contact form with cooldown + daily rate limits; Arabic name validation; ticket status tracking in admin |
| **SEO** | Dynamic sitemaps (static pages, categories, products); `robots.txt`; Open Graph / Twitter Card tags; structured data (Organization + Product) |
| **Theming** | Tailwind CSS + CSS custom properties; admin-configurable light/dark palettes persisted in `StoreSettings`; client-side theme toggle with `localStorage` sync |
| **Deployment** | Vercel-ready (serverless PostgreSQL, static files via WhiteNoise, ImageKit media CDN, SSL header handling) |

---

## 🏗 Architecture

```
durrat_tarim/          # Project settings, URLs, WSGI, context processors, email backend
├── accounts/          # Custom User, allauth adapters, login/registration views, redirects
├── catalog/           # Category, Product, Favorite, FeaturedProduct, StoreSettings models & views
├── dashboard/         # Django admin dashboards (custom ModelAdmin, charts)
├── support/           # Contact form, Ticket model, rate limiting
└── static/            # Tailwind output (output.css), animations.css, JS modules
templates/
├── base.html          # Root layout, header, footer, WhatsApp float button
├── partials/          # head.html, header.html, footer.html
├── catalog/           # Product grid, detail, featured slider, category cards
├── accounts/          # Login, signup, email verification, password reset
└── support/           # Contact form
```

### Data Model Highlights

- **User** (`accounts.models.User`): UUID PK, `email` (unique, USERNAME_FIELD), `full_name`, `preferred_language` (ar/en), `is_verified_email` property
- **Category** (`catalog.models.Category`): `name_ar`/`name_en`, `slug`, `image`, `display_order`, `is_active`
- **Product** (`catalog.models.Product`): `name_ar`/`name_en`, `description_ar`/`description_en`, `price_sar` (Decimal), `price_yer` (computed via cached rate), `category` FK, `image` + 3 extra images, `is_active`, `is_featured`, `created_at`
- **Favorite** (`catalog.models.Favorite`): User ↔ Product many-to-many with `created_at`
- **FeaturedProduct** (`catalog.models.FeaturedProduct`): Ordered slider items for homepage hero
- **StoreSettings** (`catalog.models.StoreSettings`): **Singleton** (enforced via `save()` + `delete()` overrides); holds WhatsApp number, SAR→YER rate, 10 color tokens (light/dark), SEO defaults
- **Ticket** (`support.models.Ticket`): name, email, subject, message, `status` (open/in_progress/closed/resolved), timestamps

---

## ⚙️ Setup & Development

### Prerequisites
- Python 3.11+
- `uv` (recommended) or `pip` + `venv`
- ImageKit account (for media in production)

### Local Development

```bash
# Clone & enter
cd durrat_tarim_django

# Create venv & install
uv venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"  # or: pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your keys (see Environment Variables below)

# Database
python manage.py migrate
python manage.py createsuperuser  # optional

# Static files (Tailwind already built into staticfiles/)
python manage.py collectstatic --noinput

# Run
python manage.py runserver
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DJANGO_SECRET_KEY` | ✅ | Django secret key |
| `DJANGO_DEBUG` | | `True`/`False` (default: `False`) |
| `USE_REMOTE_DB` | | `True` to use PostgreSQL (requires `POSTGRES_*` vars) |
| `POSTGRES_USER`/`PASSWORD`/`HOST`/`DB`/`PORT` | If `USE_REMOTE_DB=True` | Remote PostgreSQL connection |
| `IMAGEKIT_PRIVATE_KEY` | Prod | ImageKit private key (server-side uploads) |
| `IMAGEKIT_URL_ENDPOINT` | Prod | e.g. `https://ik.imagekit.io/your_id` |
| `RESEND_API_KEY` | Prod | Resend API key for transactional emails |
| `RESEND_SENDER` | | From address (default: `noreply@durrat-tarim.com`) |
| `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` | | Google OAuth credentials |
| `VERCEL` | On Vercel | Set to any value to enable Vercel-specific SSL/header handling |
| `MEDIA_URL` | | Media URL prefix (default: `/uploads/`) |
| `MEDIA_ROOT` | | Local media root (default: `BASE_DIR/uploads` or `/tmp/uploads` on Vercel) |

---

## 🚀 Deployment (Vercel)

The project is configured for **Vercel** with serverless functions.

### Vercel Configuration

1. **Framework Preset**: Other (or Django)
2. **Build Command**: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
3. **Output Directory**: `staticfiles`
4. **Install Command**: `pip install -r requirements.txt`
5. **Dev Command**: `python manage.py runserver`

### Required Vercel Environment Variables

All production variables from the table above, plus:
- `USE_REMOTE_DB=True`
- `POSTGRES_*` (Vercel Postgres / Neon / Supabase / etc.)
- `VERCEL=1` (auto-set by Vercel)

### Key Deployment Details

- **Static files**: WhiteNoise (`CompressedStaticFilesStorage`) serves from `staticfiles/`
- **Media**: ImageKit CDN (no local disk needed); `STORAGES["default"]` uses `catalog.imagekit_storage.ImageKitStorage`
- **SSL**: `SECURE_PROXY_SSL_HEADER` + `USE_X_FORWARDED_HOST` enabled when `VERCEL` env var is present
- **Database**: PostgreSQL with connection pooling (`CONN_MAX_AGE=300`, health checks, keepalives)
- **Sessions/CSRF**: Secure cookies in production; `CSRF_TRUSTED_ORIGINS` includes `*.vercel.app` and custom domains

---

## 🎨 Theming & Design System

### CSS Custom Properties (set via `StoreSettings` in admin)

```css
:root {
  --color-primary: #30669c;      /* Brand primary */
  --color-secondary: #08121b;    /* Dark text */
  --color-accent: #e0801f;       /* Gold/accent */
  --color-background: #f6f1ee;   /* Page background */
  --color-surface: #ffffff;      /* Card surface */
}

html.dark {
  --color-primary: #39f2f9;
  --color-secondary: #e0ebe7;
  --color-accent: #e7994b;
  --color-background: #08121b;
  --color-surface: #0c1927;
}
```

- **Fonts**: Cairo, Tajawal, El Messiri (Google Fonts, preconnected)
- **Tailwind**: Custom config extends colors using the CSS variables above (`bg-primary`, `text-accent`, etc.)
- **Dark mode**: Class-based (`html.dark`); persisted in `localStorage`; toggle in header + mobile menu

### Building CSS

```bash
# Requires Node.js + Tailwind CLI
npx tailwindcss -i ./static/css/input.css -o ./staticfiles/css/output.css --minify
# Also outputs .gz and .br via build script
```

---

## 🔐 Authentication Flow

```
Email/Password                    Google OAuth
─────────────────                 ─────────────
1. /auth/signup/                  1. /auth/login/ → "Continue with Google"
2. Email verification sent        2. Google consent screen
3. User clicks link               3. Callback → allauth creates User
4. Auto-login (ACCOUNT_LOGIN_     4. SocialAccountAdapter.populate_user()
   ON_EMAIL_CONFIRMATION)           fills full_name from first/last
5. Redirect to `next` or home       5. Auto-connect if email matches existing
```

### Key allauth Settings

```python
ACCOUNT_LOGIN_METHODS = {"email"}           # Email only, no username
ACCOUNT_EMAIL_VERIFICATION = "mandatory"    # Block login until verified
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True  # Auto-login after verify
ACCOUNT_RATE_LIMITS = {"login_failed": "5/300s"}
ACCOUNT_ADAPTER = "accounts.adapter.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "accounts.adapter.SocialAccountAdapter"
```

---

## 🛒 Catalog & WhatsApp Integration

### Product Inquiry Flow

1. User clicks **"استفسار واتساب"** on any product card/detail
2. `product_whatsapp` view builds a pre-filled Arabic message via `catalog/whatsapp.py`
3. Redirects to `https://wa.me/<number>?text=<encoded_message>`
4. Signal `product_whatsapp_clicked` fires for analytics

### Favorites Flow

1. Authenticated + verified users see heart icon on product cards
2. `add_favorite` / `remove_favorite` (POST only) toggle via AJAX-friendly redirects
3. `favorites` page lists user's favorites with checkboxes
4. `favorites_whatsapp` (POST) builds a combined message for selected products (max 10)
5. Redirects to WhatsApp with the collection message

### Arabic Search Normalization

`catalog.utils.normalize_arabic()` maps:
- Alef variants: `أ إ آ ا` → `ا`
- Yaa variants: `ى ي` → `ي`
- Teh marbuta: `ة` → `ه`

Both raw and normalized queries are searched (`icontains` on `name_ar` + `description_ar`).

---

## 💰 Currency Handling

- **Base currency**: Saudi Riyal (SAR) — stored as `Decimal` on `Product.price_sar`
- **Yemeni Rial (YER)**: Computed property `Product.price_yer` using cached `StoreSettings.currency_rate` (SAR → YER)
- **Admin**: Edit rate in `StoreSettings` singleton (cached for 5 minutes via `cache.get_or_set`)
- **Templates**: Both prices shown via `product.price_sar` and `product.price_yer`

```python
# catalog/currency.py
def get_yer_rate() -> Decimal:
    return cache.get_or_set("catalog:currency_rate", _fetch_from_db, 300)

@property
def price_yer(self) -> Decimal:
    return (self.price_sar * get_yer_rate()).quantize(Decimal("1"))
```

---

## 📧 Email (Resend)

- **Backend**: `durrat_tarim.email_backend.ResendEmailBackend` (thin wrapper around Resend HTTP API)
- **Dev**: Console backend when `DEBUG=True`
- **Templates**: allauth default templates (override in `templates/account/email/`)
- **Rate limit**: `RESEND_TIMEOUT` (default 10s)

---

## 🗂 Sitemaps & SEO

| Sitemap | Source | Frequency |
|---------|--------|-----------|
| `static` | Hardcoded view names (home, types, search, contact, auth) | weekly |
| `categories` | `Category.objects.filter(is_active=True)` | weekly |
| `products` | `Product.objects.filter(is_active=True, category__is_active=True)` | daily |

- `robots.txt` served at `/robots.txt` pointing to sitemap index
- Open Graph + Twitter Card tags in `partials/head.html` (dynamic per page)
- Structured data: `Organization` (site-wide) + `Product` (on product detail)

---

## 🧪 Testing

```bash
# Run all tests
python manage.py test

# With coverage
coverage run --source='.' manage.py test
coverage report -m
```

Key test areas:
- `accounts.tests`: Custom User, adapters, redirects, email verification
- `catalog.tests`: Models, views, WhatsApp message building, currency, search normalization
- `support.tests`: Contact form rate limiting, validation

---

## 📁 Important Files Reference

| File | Purpose |
|------|---------|
| `durrat_tarim/settings.py` | All configuration (DB, storage, allauth, email, SSL, i18n) |
| `durrat_tarim/urls.py` | Root URLconf, sitemaps, robots.txt, health check |
| `durrat_tarim/context_processors.py` | `site_context`: injects `site_settings`, `is_store_admin`, `is_store_authenticated` |
| `accounts/models.py` | Custom User model (UUID, email username) |
| `accounts/adapter.py` | allauth adapters (login redirect, social full_name population) |
| `accounts/redirects.py` | Post-login redirect logic with session preservation |
| `accounts/signals.py` | Auto-login after email confirmation |
| `catalog/models.py` | Category, Product, Favorite, FeaturedProduct, StoreSettings |
| `catalog/views.py` | All storefront views (home, search, category, product, favorites, WhatsApp) |
| `catalog/currency.py` | SAR→YER conversion with cached admin rate |
| `catalog/whatsapp.py` | WhatsApp message templates + URL building |
| `catalog/imagekit_storage.py` | Custom Django storage backend for ImageKit |
| `catalog/utils.py` | Arabic text normalization for search |
| `catalog/sitemaps.py` | StaticViewSitemap, CategorySitemap, ProductSitemap |
| `support/models.py` | Ticket model with status workflow |
| `support/views.py` | Contact form with cooldown + daily limits |
| `support/forms.py` | ContactForm with Arabic name validation |
| `dashboard/admin.py` | Custom admin dashboards, charts, ModelAdmin overrides |

---

## 🔧 Extending the Project

### Add a New Model Field
1. Add field to model in `catalog/models.py` (or relevant app)
2. Create migration: `python manage.py makemigrations`
3. Update admin in `dashboard/admin.py` if needed
4. Update templates/views as needed

### Add a New Page
1. Add view in appropriate `views.py`
2. Add URL in app's `urls.py` (include in root `urls.py` if new app)
3. Create template in `templates/<app>/`
4. Add to `StaticViewSitemap` if public

### Modify WhatsApp Message Format
Edit `catalog/whatsapp.py`:
- `product_message(request, product)` — single product inquiry
- `favorites_message(request, products)` — collection sharing

### Add a New Social Provider
1. Add to `INSTALLED_APPS`: `allauth.socialaccount.providers.<provider>`
2. Configure in `SOCIALACCOUNT_PROVIDERS` in `settings.py`
3. Add credentials to environment variables

---

## 📄 License

Proprietary — All rights reserved. Internal use only.

---

## 🤝 Contributing

Internal project — follow the existing patterns:
- **Code style**: Black + isort (configured in `pyproject.toml`)
- **Commits**: Conventional commits (`feat:`, `fix:`, `refactor:`, etc.)
- **PRs**: Required for `main`; CI runs tests + lint
- **Arabic first**: All user-facing text in Arabic; English as secondary