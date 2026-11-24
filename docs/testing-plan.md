# Durrat Tarim — Full Testing & Release-Gate Plan

> **Purpose:** Prevent production regressions by closing all test blind spots revealed by the `POST /admin/catalog/category/add/` HTTP 500 error on `durrat-tarim-dev`, establishing an automated 6-layer test suite, pre-deploy health checks, and a CI/CD release gate.

---

## 1. Incident Postmortem: `POST /admin/catalog/category/add/` (HTTP 500)

### 1.1 Observed Error on Host (`durrat-tarim-dev` / `dpl_6iau8gxhh2tX8gUhoAfq1cq67yqR`)

Three `500 Internal Server Error` events were logged in Vercel Runtime Errors for route `POST /admin/catalog/category/add/`:

```text
File "/var/task/catalog/admin.py", line 522, in save_model
  super().save_model(request, obj, form, change)
File "/var/task/catalog/models.py", line 240, in save
  super().save(*args, **kwargs)
...
File "/var/task/catalog/imagekit_storage.py", line 52, in _save
  response.raise_for_status()
requests.exceptions.HTTPError: 403 Client Error: Forbidden for url: https://upload.imagekit.io/api/v1/files/upload
```

### 1.2 Root Causes

1. **ImageKit Upload Rejected (`403 Forbidden`):**
   - `durrat-tarim-dev` has `IMAGEKIT_PRIVATE_KEY` and `IMAGEKIT_URL_ENDPOINT` configured in Vercel, so `durrat_tarim/settings.py` activates `catalog.imagekit_storage.ImageKitStorage`.
   - When `ImageKitStorage._save()` POSTs to `https://upload.imagekit.io/api/v1/files/upload`, ImageKit returns `403 Forbidden` (invalid/revoked/whitespace-padded private key, account restriction, or upload payload rejection — e.g. `fileName` containing a folder slash `"categorys/<uuid>.ext"` without separating `folder` and `fileName`, and no response body logged before `raise_for_status()`).
2. **Unhandled Storage Exceptions in Django Admin:**
   - In `catalog/admin.py` (`CategoryAdmin.save_model` lines 518–522 and `ProductAdmin`), **creates (`change=False`)** bypass `handle_image_replacement()` / `_validate_image()` and call `super().save_model()`, which executes `ImageField.pre_save` → `ImageKitStorage._save()`.
   - Neither create nor edit catches storage/HTTP failures (`requests.RequestException`, `OSError`), so any third-party upload failure or `403` crashes the admin view with an unhandled HTTP `500` instead of surfacing a readable Arabic error message to the staff user.
3. **Why Existing Tests Missed It:**
   - All existing unit/integration tests either avoid `ImageField` uploads with real files or run locally without exercising `ImageKitStorage`, admin `POST` create/edit forms, or live host environment credentials.

---

## 2. Current Test Inventory & Coverage Gap Audit

| Area / Module | Existing Test File | Current Coverage | Risk Level | Key Blind Spots |
| :--- | :--- | :--- | :--- | :--- |
| **ImageKit Storage** (`catalog/imagekit_storage.py`) | *None* | **0%** | Critical | `_save()`, `_find()`, `exists()`, `delete()`, `url()`, `get_available_name()`, Basic auth formatting, folder/filename handling, `401`/`403`/`500`/timeout handling & response error logging |
| **Image Validation & Cleanup** (`catalog/image_storage.py`) | *None* | **0%** | Critical | `_validate_image()` (extensions, 5 MB limit, min/max dimensions, corrupt images, content-type mismatch), `_require_durable_storage()`, `handle_image_replacement()`, `handle_image_deletion()`, `_cleanup_old_image()` |
| **Django Admin Forms & CRUD** (`catalog/admin.py`, `accounts/admin.py`, `support/admin.py`) | Partial in `catalog/test_hierarchy.py` (changelist/form checks) | Low | Critical | No end-to-end `POST` add/change/delete tests with image uploads for `CategoryAdmin` and `ProductAdmin`; no tests ensuring storage failures fail gracefully instead of returning 500; `FeaturedProductAdmin` & `StoreSettingsAdmin` & `TicketAdmin` POST flows |
| **Catalog Models, Views & Hierarchy** (`catalog/models.py`, `views.py`, `templatetags/`) | `catalog/tests.py`, `catalog/test_hierarchy.py`, `catalog/test_theme.py` | Good | Medium | Edge cases under `ImageField` create/update/delete, pagination bounds, 404/inactive parent chains, RTL/theme CSS generation under empty DB |
| **Catalog Utilities** (`catalog/whatsapp.py`, `catalog/currency.py`, `catalog/utils.py`, `catalog/sitemaps.py`) | Partial | Low–Medium | Medium | WhatsApp URL formatting with missing/non-numeric numbers, currency conversion cache invalidation, empty-DB sitemap rendering |
| **Dashboard App** (`dashboard/views.py`, `urls.py`) | *None* | **0%** | High | `@staff_member_required` enforcement (anonymous, non-staff user, staff user), template context counts (`total_products`, `total_categories`, `total_tickets`, `pending_tickets`) |
| **Support App** (`support/views.py`, `forms.py`, `models.py`) | `support/tests.py` (1 KB) | Minimal | Medium | Validation errors, spam/length bounds, POST submission + email notification failure handling |
| **Accounts App & OAuth** (`accounts/views.py`, `adapter.py`, `redirects.py`, `signals.py`) | `accounts/tests.py` (8.2 KB) | Moderate | High | Safe `next` open-redirect guards, Google OAuth callback/adapter edge cases, passwordless/duplicate email handling |
| **Project Infra** (`durrat_tarim/context_processors.py`, `sitemap_views.py`, `email_backend.py`) | `durrat_tarim/tests.py` (`ResendEmailBackend` only) | Partial | Medium | Context processor queries on empty DB, HTTP timeout/failure on Resend, `robots.txt` / sitemap index routes |
| **Staging / Host Smoke & Health Checks** | *None* | **0%** | Critical | No automated post-deploy verification of DB connectivity, migrations, `ImageKit` credentials, static assets, or key routes on `durrat-tarim-dev` |
| **CI/CD Release Gate** | *None* | **0%** | Critical | Broken code or untested admin flows can reach `main` without automated checks or coverage thresholds |

---

## 3. Immediate Reliability Fixes (Prerequisite Alongside Testing)

Before considering `Category` / `Product` admin uploads production-ready:

1. **Diagnose & Fix ImageKit 403 (`catalog/imagekit_storage.py` + Vercel env):**
   - Inspect ImageKit API error details cleanly by logging `response.status_code` and `response.text[:500]` (without ever logging `IMAGEKIT_PRIVATE_KEY`) before calling `response.raise_for_status()`.
   - Verify whether `IMAGEKIT_PRIVATE_KEY` on `durrat-tarim-dev` (and local `.env`) has valid upload permissions, no accidental quotes/whitespace, and uses the Private Key (not Public Key).
   - Check ImageKit `/api/v1/files/upload` payload format (`fileName` vs `folder` + `fileName` while ensuring `url(name)` still resolves deterministically via `response.json().get("filePath")` or matching `fileName`).
2. **Harden Admin Upload Flows (`catalog/admin.py`, `catalog/image_storage.py`):**
   - Validate images with `_validate_image()` on **both create (`change=False`) and update (`change=True`)** before saving to DB/storage.
   - Catch storage/network errors cleanly inside admin form validation / `save_model` (or form `clean_*`) so failed uploads add a clear Arabic error (`messages.error` or `ValidationError`) instead of throwing HTTP 500, and roll back / avoid orphaned DB records if upload fails.

---

## 4. Six-Layer Testing Architecture

### Layer 1: Unit Tests (Fast, Isolated, Mocked External APIs)
- **`catalog/test_storage.py`** (new):
  - `ImageKitStorage._save()`: verifies multipart upload payload, Basic Auth `(private_key, "")`, `useUniqueFileName="false"`, return path, logging on non-2xx (`401`, `403`, `500`), and timeout propagation.
  - `ImageKitStorage._find()`, `exists()`, `delete()`, `url()`, `get_available_name()`, `size()`, `open()`.
  - `image_storage._validate_image()`: valid JPG/PNG/WEBP, invalid extension (`.gif`, `.svg`, `.exe`), >5 MB file, <100x100 px, >4096x4096 px, content-type/extension mismatch, corrupt bytes, and `seek(0)` verification.
  - `image_storage._require_durable_storage()`: `DEBUG=False` + `/tmp` without ImageKit raises `RuntimeError`; allowed when `IMAGEKIT_PRIVATE_KEY` is configured or `DEBUG=True`.
  - `handle_image_replacement()` & `handle_image_deletion()` & `_cleanup_old_image()`: verifies old image deleted only when unreferenced by other rows; failed replacement does not overwrite DB or delete old image.
- **`catalog/test_utils.py`** (new or expanded):
  - `catalog/currency.py`: cache hit/miss, `invalidate_rate_cache()`, fallback defaults.
  - `catalog/whatsapp.py`: valid/invalid phone numbers, RTL Arabic message encoding, empty phone handling.

### Layer 2: Django Admin CRUD & Upload Integration Tests
- **`catalog/test_admin.py`** (new):
  - Generate real in-memory PNG/JPEG/WEBP test images using `Pillow` (`SimpleUploadedFile`).
  - **CategoryAdmin (`POST /admin/catalog/category/add/`, `change/`, `delete/`):**
    - Create root category with valid image (mocked `FileSystemStorage` & mocked `ImageKitStorage` returning 200).
    - Create child category inside empty parent vs. **blocked** creation inside parent that already holds products (verifying clean form validation error, not 500).
    - Replace image on edit (verifies old image cleanup); delete single & bulk categories (verifies image deletion hook).
    - **Failure resilience tests:** Mock `ImageKitStorage._save()` raising `requests.HTTPError` (`403 Forbidden`, `401 Unauthorized`, `500`) and `requests.Timeout` — assert response is **never 500**, staff sees an error message, and no orphan DB row is persisted.
  - **ProductAdmin (`POST /admin/catalog/product/add/`, `change/`, `delete/`):**
    - Create product on leaf category with valid image; reject non-leaf category; reject invalid/corrupt image; handle storage HTTP 403/500 without 500 error page.
  - **StoreSettingsAdmin & FeaturedProductAdmin & TicketAdmin:**
    - Valid and invalid hex colors, singleton preservation, featured product constraints, ticket status transitions.

### Layer 3: App Functional & Security Regression Tests
- **`dashboard/tests.py`** (new):
  - Anonymous user → redirect to login (`302`).
  - Authenticated non-staff user → denied/redirected (`302` or `403`, never `200`).
  - Staff user → `200`, accurate counts (`total_products`, `total_categories`, `total_tickets`, `pending_tickets`).
- **`support/tests.py`** (expand):
  - Valid ticket creation, required field validation, oversized input bounds, honeypot/rate/email failure safety.
- **`accounts/tests.py`** (expand):
  - Open-redirect protection (`?next=https://evil.com`), login/signup/profile flows, Google OAuth adapter & duplicate email handling.
- **`durrat_tarim/tests.py`** (expand):
  - `context_processors` on an empty database (0 categories, 0 `StoreSettings`), `sitemap_views` (`sitemap.xml` HTTP 200 on empty & populated DB), `ResendEmailBackend` HTTP error & timeout handling.

### Layer 4: Database, Migration & Django Deployment Checks
Automated commands required in every PR / pre-deploy check:
- Pending migration drift check: `uv run python manage.py makemigrations --check --dry-run`
- Django system & security check: `uv run python manage.py check` and production-like `DJANGO_DEBUG=False` check.
- Migration reversibility & Postgres query parity (recursive CTE in `catalog/views.py`, `Case/When` annotations in `catalog/admin.py`) verified against PostgreSQL (CI `postgres:16` service or dev DB test schema).

### Layer 5: Live Host / Staging Smoke & External Service Health Checks
1. **Management Command `catalog/management/commands/check_services.py`** (new):
   - Verifies DB connection (`SELECT 1` + pending migration check).
   - Verifies static assets exist (`static/css/output.css`, `static/images/product-placeholder.svg`).
   - Optional `--check-imagekit` flag: authenticates against ImageKit (and with `--write-test`, uploads a tiny 100x100 PNG test file to a `_healthcheck/` prefix and immediately deletes it) so broken keys/403s are caught **before** an admin user clicks Save.
2. **Post-Deploy Smoke Script `scripts/smoke_test.py`** (new):
   - Accepts `--base-url https://durrat-tarim-dev.vercel.app`.
   - Verifies HTTP `200` on `/`, `/products/types/`, `/products/search/`, `/contact/`, `/admin/login/`, `/sitemap.xml`, `/static/css/output.css`, `/static/images/product-placeholder.svg`.
   - Verifies no server error signatures (`Server Error (500)`, uncaught tracebacks).
   - Optional authenticated admin read/smoke check using test credentials from environment variables (never hardcoded).

### Layer 6: CI/CD Release Gate (Before Anything Reaches `main`)
Add `.github/workflows/ci.yml` running on every push and PR to `dev/*` and `main`:
1. Install Python 3.13 + `uv sync --frozen` (+ Node 24 for Tailwind CSS verification if `input.css`/templates change).
2. Run lint/format check (`uv run ruff check .`).
3. Run `uv run python manage.py makemigrations --check --dry-run`.
4. Run full test suite with coverage (`uv run pytest` or `coverage run manage.py test` with `--fail-under=85`).
5. **Production Promotion Checklist** (required before merging `dev/integration` → `main`):
   - CI green on `dev/integration`
   - `manage.py check_services --check-imagekit --write-test` passed against dev environment
   - `scripts/smoke_test.py --base-url https://durrat-tarim-dev.vercel.app` passed
   - Manual admin test: create & delete a test category + product with image on `durrat-tarim-dev`
   - Vercel Runtime Errors (`get_runtime_errors`) = `0` on `durrat-tarim-dev`

---

## 5. Execution Phases & Verification Commands

| Phase | Scope | Verification Command (Windows PowerShell) |
| :--- | :--- | :--- |
| **Phase 1** | Fix ImageKit 403 root cause + add graceful admin error handling & logging | `uv run python manage.py check` |
| **Phase 2** | Add Layer 1 Unit Tests (`test_storage.py`, `test_utils.py`) | `uv run python manage.py test catalog.test_storage catalog.test_utils` |
| **Phase 3** | Add Layer 2 Admin POST & Upload Failure Tests (`test_admin.py`) | `uv run python manage.py test catalog.test_admin` |
| **Phase 4** | Add Layer 3 App Gap Tests (`dashboard`, `support`, `accounts`, `durrat_tarim`) | `uv run python manage.py test` |
| **Phase 5** | Add `check_services`, `scripts/smoke_test.py`, Coverage Gate & `.github/workflows/ci.yml` | `uv run coverage run manage.py test; uv run coverage report --fail-under=85` |
| **Phase 6** | Deploy to `durrat-tarim-dev`, run live smoke test + ImageKit health check, verify 0 Vercel runtime errors | `uv run python scripts/smoke_test.py --base-url https://durrat-tarim-dev.vercel.app` |
