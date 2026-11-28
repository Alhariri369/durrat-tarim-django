---
name: git-reconciliation-plan
description: Plan for per-agent branch commits and merge into dev/integration
metadata:
  type: project
---

File ownership for per-agent branches (all built on main = 20a2f66):

- dev/seo-meta-tags (A1): templates/partials/head.html — commit 3b84717 (currently on dev/seo-structured-data, must move) + working-tree head.html refinements (WebSite JSON-LD, dynamic theme-color, robots_content).
- dev/seo-structured-data (A2): catalog/templatetags/catalog_tags.py, catalog/models.py (get_absolute_url + help_text), catalog/views.py (breadcrumbs + robots_content), templates/{type_products,search,product_details,types,index}.html, templates/catalog/partials/{breadcrumb,category,product}_json_ld.html (new).
- dev/seo-sitemap (A3): catalog/sitemaps.py (StaticViewSitemap.lastmod), durrat_tarim/sitemap_views.py (new), durrat_tarim/urls.py (sitemap_views + robots.txt).
- dev/theme-admin: catalog/admin.py (_ColorPreviewAdminMixin + color swatches).
- dev/theme-templates (NEW branch, create from main): templates/partials/theme-variables.html (new), templates/login.html, templates/register.html (Google button theme tokens).
- dev/theme-static: static/css/input.css (theme tokens), static/css/output.css (built).

Do NOT commit: db.sqlite3, docs/ (untracked local artifacts).
Drop stash@{0} (old buggy WIP on dev/integration, superseded, contains 2-placeholder format_html bug).
After per-agent commits: merge all into dev/integration, run manage.py test (sqlite) + npm run build, create PR dev/integration -> main, final report.
No git push unless user asks.