# Session State Reset — Durrat Tarim Django

**Date:** 2026-11-22  
**Branch:** `dev/integration`  
**Purpose:** Snapshot for restarting the conversation. No code was written or changed in this session.

---

## What exists on disk (untracked, not committed)

| File | Source | Status |
|------|--------|--------|
| `docs/recon.md` | Prior B1 audit (11-20) | Untracked, pre-existing |
| `docs/master-plan.md` | Prior planning (11-20) | Untracked, pre-existing |
| `docs/theme-plan.md` | Prior B1 audit output (11-20) | Untracked, pre-existing |
| `docs/seo-implementation.md` | Prior A4 docs (11-22) | Untracked, references commit `5461a3c` |
| `vercel-get-started.md` | Vercel onboarding playbook | Untracked, reference file in repo root |

None of these were created or edited by me in this session. They are carried over from prior work.

---

## Git state

```
Current branch: dev/integration
Recent commits:
  5461a3c chore(build): rebuild output.css after merge verification
  2e09d93 merge(seo-theme): A1 meta tags, A2 structured data, A3 sitemap, B theme work
  11db2fd feat(theme): Tailwind v4 theme tokens in input.css and built output.css
  55490a2 feat(theme): theme CSS variables partial + themed Google auth buttons
  1322cc8 feat(theme): color swatch previews in StoreSettings admin

Untracked:
  .claude/
  db.sqlite3
  docs/seo-implementation.md
  docs/theme-plan.md
  vercel-get-started.md
```

- `main` is untouched. No merge with `main` has happened or been attempted in this session.
- All theme (B1–B4) and SEO (A1–A4) branches were merged into `dev/integration` in prior work.
- Nothing pushed unless explicitly asked. `db.sqlite3` and `.env` are not committed.

---

## Vercel state

| Item | Value |
|------|-------|
| Dev project ID | `prj_wLRYiS7DRJuYCuR2uZLFwbmh41uH` |
| Dev project name | `durrat-tarim-dev` |
| Org/team ID | `team_jJPnNSSPRGvxHzwhlV75cp0x` |
| Dev URL | `https://durrat-tarim-dev.vercel.app` |
| Prod URL | `https://durrattarim-2j37ccl03-batmanors-projects.vercel.app` (domains: durttrim.vercel.app etc.) |
| `vercel.json` | Routes all `/(.*)` to `durrat_tarim/wsgi.py` via `@vercel/python` |
| Build command | `bash setup.sh` |
| Install command | `pip install -r requirements.txt` |
| Vercel CLI version | 54.18.2 (outdated; latest 66.6.0) |

- Dev host is deployed and live, isolated from prod.
- Prod was never touched by any deploy in this session.
- CLI `whoami` works (authenticated as batmanor). Deploy mutations previously hit classifier timeouts; user ran the deploy themselves successfully.

---

## Theme system (Task B) — current state

**Colors (light / dark):**

| Token | Light | Dark |
|-------|-------|------|
| primary | `#30669c` (blue) | `#39f2f9` (cyan) |
| secondary | `#08121b` (navy) | `#e0ebe7` |
| accent | `#e0801f` (orange) | `#e7994b` |
| background | `#f6f1ee` (off-white) | `#08121b` |
| surface | `#ffffff` (white) | `#0c1927` |

- `static/css/input.css` — Tailwind v4 `@theme` with primary, accent, background, text, border, focus + rose palette + 3 font tokens. Missing `surface` and `secondary` in `@theme` (noted gap in recon).
- `static/css/output.css` — built output, committed (5461a3c).
- `catalog/models.py` — `StoreSettings` singleton with 10 color fields (5 light + 5 dark), defaults matching the table above.
- `templates/partials/head.html` — injects CSS custom properties inline; `theme-color` meta now dynamic per A1/A2 work.
- `templates/partials/theme-variables.html` — extracted CSS variables partial (per SEO docs).

**Lilac investigation:** Searched entire codebase for "lilac" and common lilac hex codes (c8a2d8, d8b4e2, e0b0ff, b4a7d6, 9370db, baa1cd, d8bfd8, thistle, plum, orchid). **Zero results.** No lilac exists anywhere — not in input.css, output.css, theme-plan.md, StoreSettings defaults, or any git branch.

**Theme plan status (from master-plan.md):**
- B1 (audit → theme-plan.md): ✅ Complete, approved
- B2 (StoreSettingsAdmin): pending
- B3 (templates): pending
- B4 (static/input.css @theme): pending
- B5 (theme tests): pending, blocked by API rate limits/credits previously

Sequencing rule: B1 → B2/B3/B4 (parallel) → B5. B1 is done; B2–B4 can start but have not been started in this session.

---

## SEO system (Task A) — current state

Per `docs/seo-implementation.md` (referencing commit `5461a3c`):

- A1 (meta tags): dynamic title, description, OG, Twitter, canonical, robots meta, Google verification, dynamic theme-color — delivered
- A2 (structured data): Product, CollectionPage, BreadcrumbList JSON-LD via `_json_ld` serializer — delivered
- A3 (sitemap + robots): sitemap classes wired in urls.py, request-aware views, robots.txt — delivered
- A4 (docs): `docs/seo-implementation.md` — delivered

52 tests pass on `dev/integration`. `npm run build` succeeds.

---

## What I did in this session

Nothing code-related. I:
- Read `docs/recon.md`, `docs/master-plan.md`, `docs/theme-plan.md`, `docs/seo-implementation.md`
- Read `.vercel/project.json`
- Read `vercel-get-started.md`
- Confirmed lilac does not exist anywhere in the codebase
- Wrote this reset file

I did not write code, commit, push, merge, deploy, or create any agents.

---

## Security constraints (verbatim, still in force)

- `db.sqlite3` must not be committed
- No push without asking
- No merge with `main`
- Do not print or commit credentials/secrets (`.env` contains real secrets: RESEND_API_KEY, GOOGLE_CLIENT_ID/SECRET, IMAGEKIT keys, Supabase creds)

---

## If you want to resume

Tell me what to do next. Options that are safe without further approval:
- Read more files / inspect current state
- Answer questions about the plan or codebase
- Help you decide what to do next

Actions that require your explicit ask first:
- Write any code
- Create or switch branches
- Commit anything
- Push to any remote
- Merge `dev/integration` → `main`
- Deploy to Vercel
- Add lilac (or any other) colors
- Create/spawn agents
