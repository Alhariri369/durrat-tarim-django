# Execution Prompt: Fix Category Admin 500 & Implement Full Testing Release Gate

Copy and run the prompt below (or start it with `/swarm` if you want parallel execution across specialists):

---

```text
You are working in `E:\Git_files\durrat_tarim_django` on branch `dev/integration`.
Read `docs/testing-plan.md` first — it is the source-of-truth specification for this task.

## Strict Safety & Environment Rules
1. Python package manager is `uv` (`uv run`, `uv add --dev`, `uv sync`). NEVER use raw `pip`.
2. This shell is Windows PowerShell 5.1: ALWAYS chain commands with `;`, NEVER `&&`.
3. NEVER commit or print `.env`, `db.sqlite3`, `db.sqlite3.bak`, `IMAGEKIT_PRIVATE_KEY`, `POSTGRES_PASSWORD`, or any secrets.
4. NEVER modify `main` branch, production Vercel project (`durrat_tarim`), or production Supabase database. All dev/staging work targets `dev/integration` and `durrat-tarim-dev` (`https://durrat-tarim-dev.vercel.app`) only.
5. Do NOT leave test artifacts/categories/products behind in the dev Supabase database after running live verification.

## Background Incident to Fix First
On `durrat-tarim-dev`, `POST /admin/catalog/category/add/` crashed with HTTP 500:
`catalog/admin.py:522 -> Category.save -> catalog/imagekit_storage.py:52 (_save): requests.exceptions.HTTPError: 403 Client Error: Forbidden for url: https://upload.imagekit.io/api/v1/files/upload`.
Also, `CategoryAdmin.save_model` and `ProductAdmin` skip `_validate_image()` on object creation (`change=False`) and do not catch storage/HTTP exceptions gracefully.

## Required Deliverables (Execute in Order)

### Phase 1: Diagnose & Fix the ImageKit 403 & Admin Crash
1. Inspect `catalog/imagekit_storage.py`, `catalog/image_storage.py`, and `catalog/admin.py`.
2. Check ImageKit upload API requirements (`fileName` vs `folder` + `fileName`, `useUniqueFileName`, Basic Auth header) and inspect safe (non-secret) key/endpoint formatting in local `.env` and `durrat-tarim-dev` (e.g., check key prefix `private_`, whitespace, URL endpoint format without printing secret values).
   - If the `IMAGEKIT_PRIVATE_KEY` on `durrat-tarim-dev` itself is invalid/restricted and cannot be fixed from code, report that clearly to the user after fixing the code issues.
3. Update `catalog/imagekit_storage.py`:
   - Properly handle folder + fileName if needed while preserving deterministic `url(name)` paths.
   - Log sanitized non-secret status + response body details on failed HTTP responses before `raise_for_status()`.
4. Update `catalog/admin.py` (and `catalog/image_storage.py` if needed):
   - Validate uploaded images via `_validate_image()` on BOTH add (`change=False`) and change (`change=True`) for `CategoryAdmin` and `ProductAdmin`.
   - Wrap image upload/save failures cleanly so `ImageKitStorage` / `requests.RequestException` / storage `OSError` never triggers an unhandled HTTP 500 in Django Admin — surface a clean Arabic error message (`messages.error` or form `ValidationError`) and ensure no orphaned DB row is saved when image upload fails.

### Phase 2: Unit & Storage Test Suite
1. Add dev test dependencies if helpful using `uv add --dev coverage ruff` (check `pyproject.toml` first).
2. Create `catalog/test_storage.py`:
   - Full mocked HTTP tests for `ImageKitStorage` (`_save`, `_find`, `exists`, `delete`, `url`, `get_available_name`, `size`, `open`, and `401`/`403`/`500`/timeout failure logging).
   - Full tests for `catalog/image_storage.py` (`_validate_image` with Pillow-generated valid/invalid/oversized/tiny/corrupt/mismatched images, `_require_durable_storage` under `DEBUG=False`, `handle_image_replacement`, `handle_image_deletion`, `_cleanup_old_image`).
3. Add or expand utility tests (`catalog/test_utils.py`):
   - `catalog/currency.py` and `catalog/whatsapp.py` edge cases.

### Phase 3: Admin CRUD & Failure-Resilience Integration Tests
Create `catalog/test_admin.py` testing real Django Admin `POST` flows with `Pillow` in-memory `SimpleUploadedFile` images:
1. `CategoryAdmin`: add root, add child, block adding child under product-holding parent, edit/replace image, delete single & bulk (verifying cleanup).
2. `ProductAdmin`: add on leaf category, block add on non-leaf category, edit/replace image, delete.
3. Storage failure injection: force `ImageKitStorage._save` to raise `HTTPError(403)`, `HTTPError(500)`, and `Timeout` during Admin `POST /admin/catalog/category/add/` and `/admin/catalog/product/add/` — verify response is NEVER HTTP 500, clear Arabic error feedback is displayed, and no orphaned DB row exists.
4. `StoreSettingsAdmin`, `FeaturedProductAdmin`, and `TicketAdmin` basic CRUD validation tests.

### Phase 4: Fill Remaining App Coverage Gaps
1. Create `dashboard/tests.py`: staff-only access control (anonymous redirect, non-staff blocked, staff 200) and accurate summary metrics.
2. Expand `support/tests.py`: valid submission, field validation errors, long-input rejection, email failure safety.
3. Expand `accounts/tests.py`: open-redirect safety (`?next=`), auth/OAuth adapter edge cases.
4. Expand `durrat_tarim/tests.py`: empty-DB `context_processors`, `/sitemap.xml` & `/robots.txt` rendering, `ResendEmailBackend` error/timeout cases.

### Phase 5: Health Checks, Smoke Suite & CI Release Gate
1. Create management command `catalog/management/commands/check_services.py`:
   - Checks DB connectivity + unapplied migrations (`MigrationExecutor`), required static files (`output.css`, `product-placeholder.svg`), and optional `--check-imagekit` (and `--write-test` that uploads and immediately deletes a tiny test PNG).
2. Create `scripts/smoke_test.py`:
   - Verifies live HTTP `200` and non-500 body across `/`, `/products/types/`, `/products/search/`, `/contact/`, `/admin/login/`, `/sitemap.xml`, `/static/css/output.css`, `/static/images/product-placeholder.svg`.
3. Create `.github/workflows/ci.yml`:
   - Runs `ruff check .`, `manage.py makemigrations --check --dry-run`, `manage.py check`, and full test suite with `coverage` >= 85% gate on PRs/pushes.

### Phase 6: Full Verification & Staging Deployment
1. Run locally (using local test settings / mocked storage):
   - `uv run ruff check .`
   - `uv run python manage.py makemigrations --check --dry-run`
   - `uv run coverage run manage.py test`
   - `uv run coverage report --fail-under=85`
2. Ensure `.vercelignore` excludes `.env`, `db.sqlite3*`, `.venv/`, `.superdesign/`, etc.
3. Run `uv run python manage.py collectstatic --noinput --clear`, deploy to `durrat-tarim-dev` (`vercel --prod --yes`), and run:
   - `uv run python scripts/smoke_test.py --base-url https://durrat-tarim-dev.vercel.app`
   - `uv run python manage.py check_services --check-imagekit` (verify ImageKit check status safely without leaking secrets)
   - Inspect Vercel runtime errors on `durrat-tarim-dev` to confirm zero new errors.
4. Summarize exact root cause fixed, all new tests added, coverage %, CI gate added, and whether manual ImageKit key action is required (if 403 was caused by an invalid key in Vercel/ImageKit).
```
