---
name: "Durrat-Tarim-Design-System"
version: "1.0"
taste_dials:
  design_variance: 6
  motion_intensity: 3
  visual_density: 3
tokens:
  colors:
    background: "#f7f3fa"
    surface: "#ffffff"
    primary: "#6b4c8c"
    secondary: "#1f1629"
    accent: "#a974c4"
    gold: "#b88928"
    gold-soft: "#f6efe0"
    whatsapp: "#25d366"
    border: "color-mix(in srgb, var(--color-secondary) 12%, transparent)"
  typography:
    font-display: "'El Messiri', 'Tajawal', system-ui, sans-serif"
    font-sans: "'Tajawal', system-ui, -apple-system, sans-serif"
---

# 1. Visual Theme & Atmosphere

**1-Line Design Read:**
> *"An editorial Gulf & Hadhrami couture lookbook — pairing quiet gallery surfaces, El Messiri calligraphic display typography, crisp 1px architectural hairlines, and 3:4 portrait garment framing with effortless one-tap WhatsApp concierge inquiry."*

**Domain & Character:**
Durrat Tarim (**درة تريم**) is an Arabic-first (`dir="rtl"`) modest fashion and abaya boutique rooted in Tarim, Hadhramaut, serving women across Yemen and Saudi Arabia via personal WhatsApp consultation. The interface evokes a daylight-lit couture showroom: calm gallery negative space, vertical 3:4 garment photography that honors full-length abaya and dress silhouettes, calligraphic-inspired display headings, and understated antique-gold accents drawn from the brand's calligraphic gown emblem (`static/images/logo-gold-transparent.png`).

- **`DESIGN_VARIANCE`: `6 / 10`** — Editorial split-grid hero, asymmetric section headers, and numbered architectural steps balanced by a disciplined 2-column mobile / 4-column desktop lookbook grid.
- **`MOTION_INTENSITY`: `3 / 10`** — Quiet luxury restraint: crisp `180ms–250ms` property-specific transitions (`transition-colors`, `transition-opacity`, `transition-transform`), subtle `1.03x` fabric zoom on hover, zero 3D card tilt, zero infinite pulse glows, and full `prefers-reduced-motion` compliance.
- **`VISUAL_DENSITY`: `3 / 10`** — Generous gallery breathing room; cards carry only essential garment metadata (portrait frame, corner favorite toggle, title, dual-currency SAR/YER price, and single WhatsApp inquiry CTA).

---

# 2. Color Palette & Roles

Core palette tokens map directly to the admin-editable `StoreSettings` singleton (`templates/partials/theme-variables.html`) with static defaults in `static/css/input.css`:

| Semantic Role | CSS Custom Property | Default Value | Usage Rules |
| :--- | :--- | :--- | :--- |
| **Gallery Canvas** | `--color-background` | `#f7f3fa` | Page background and subtle inset image wells. Never overlay noisy multi-stop neon/purple mesh blobs. |
| **Elevated Surface** | `--color-surface` | `#ffffff` | Cards, sticky header, mobile drawer, form inputs on focus, and structured panels. |
| **Couture Primary** | `--color-primary` | `#6b4c8c` | Brand wordmark, primary solid buttons, active navigation state, and SAR price emphasis. |
| **Editorial Ink** | `--color-secondary` | `#1f1629` | Primary body copy, garment titles, and high-contrast dark consultation banners. Never drop body copy below `/65` opacity (WCAG AA). |
| **Interactive Accent** | `--color-accent` | `#a974c4` | Subtle focus highlights, active indicators, and understated hover accents. Never spam as `bg-accent/10` rounded pills above every heading. |
| **Emblem Gold** | `--color-gold` | `#b88928` | 1px editorial eyebrow rules, subtle divider accents, and framing around `logo-gold-transparent.png`. |
| **Concierge CTA** | `--color-whatsapp` | `#25d366` (`#1da851` text/hover) | Direct WhatsApp product and favorites inquiry actions. |
| **Hairline Border** | `--color-border` | `secondary @ 12%` | Crisp `1px` architectural borders separating surfaces without heavy drop shadows. |
| **Status Semantic** | `success` / `error` / `warning` | `#059669` / `#dc2626` / `#d97706` | Inline validation messages and `border-s-4` toast notifications. |

---

# 3. Typography Rules

- **Display Font (`font-display` -> `El Messiri`)**:
  - Used for `h1`, `h2`, brand wordmark, and editorial step numerals (`01`, `02`, `03`).
  - Weights: `600` (SemiBold) and `700` (Bold). Line-height: `1.2`–`1.3` for Arabic display titles.
- **Interface & Body Font (`font-tajawal` -> `Tajawal`)**:
  - Used for navigation, buttons, product card titles (`h3`), descriptions, form controls, and metadata.
  - Weights: `400` (Regular), `500` (Medium), `700` (Bold), `800` (ExtraBold). Body line-height: `1.7` (`leading-relaxed`).
- **Numeric Discipline (`tabular-nums`)**:
  - Mandatory on all SAR (`ر.س`) and YER (`ر.ي`) prices, phone numbers, working hours, pagination counters, and dashboard KPIs.
- **Scale Hierarchy**:
  - Hero Display (`h1`): `text-3xl sm:text-4xl lg:text-5xl` (strictly 1–3 concise lines on `1440x900`).
  - Section Heading (`h2`): `text-2xl sm:text-3xl lg:text-4xl`.
  - Card Title: `text-sm sm:text-base font-bold leading-snug line-clamp-2`.

---

# 4. Component Stylings

- **Navigation Header**: Fixed top bar (`h-18 lg:h-20`) with `bg-surface/95 backdrop-blur-md` and `1px` `border-secondary/10` bottom hairline. Uncropped portrait gold logo (`width="34" height="45" object-contain`) paired with solid `font-display` wordmark.
- **Buttons**:
  - Radius: `rounded-xl` (`0.75rem`) for page-level CTAs, `rounded-lg` (`0.5rem`) inside compact product cards.
  - Minimum touch height: `min-h-11` (`44px`).
  - Focus state: `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2`.
  - In-flight submission: Keep enabled until submit; disable during active submission with inline spinner while preserving label text width.
- **Product Cards (`product_card.html`)**:
  - Solid `bg-surface rounded-xl border border-secondary/10` (`.atelier-card`).
  - Top `aspect-[3/4]` image container with subtle `scale-[1.03]` image hover (`img-zoom`) and top-end `44x44px` circular Favorite toggle button.
  - Body (`min-w-0 text-start`): Category caption, 2-line clamped title link, hairline-separated `tabular-nums` SAR + YER price stack, and one primary WhatsApp inquiry CTA.
- **Forms & Inputs**:
  - Explicit `<label>` for every input (`sr-only` permitted only for compact search bars).
  - Logical padding (`ps-*`, `pe-*`) so RTL icons never overlap typed text.
  - Email and phone fields enforce `dir="ltr"`, `spellcheck="false"`, accurate `type`/`inputmode`/`autocomplete`, and format placeholders ending with `…`.

---

# 5. Layout Principles

- **Container Max-Width**: `max-w-7xl mx-auto px-4 sm:px-6 lg:px-8`.
- **Fixed Header Offset**: `<main id="main-content">` reserves `pt-18 lg:pt-20` so fixed navigation never overlaps page headers or breadcrumbs.
- **Vertical Rhythm**: `py-12 md:py-20` between major homepage sections; `py-10 md:py-14` on internal catalog, detail, contact, and dashboard pages.
- **RTL/LTR Logical Properties**: Always use `ms-*`, `me-*`, `ps-*`, `pe-*`, `start-*`, `end-*`, `border-s-*`, `rounded-s-*`, `rounded-e-*`, and `text-start` so Arabic (`rtl`) and future English (`ltr`) layouts mirror cleanly.

---

# 6. Depth & Elevation

- **Hairline First**: Separate surfaces primarily through canvas-vs-surface contrast (`#f7f3fa` vs `#ffffff`) and `1px` `border-secondary/10` hairlines.
- **Restrained Shadows**: Use subtle `shadow-xs` / `shadow-sm` on cards and `shadow-lg` only on floating elements (WhatsApp concierge button, toast alerts, mobile drawer).
- **Z-Index Scale**: Sticky page bars `z-20`, floating WhatsApp button `z-40`, fixed header `z-50`, toast notifications `z-60`.

---

# 7. Do's and Don'ts

### Do
- Frame garments in `3:4` or `4:5` portrait aspect ratios with explicit `width` and `height` attributes.
- Use `font-display` (`El Messiri`) with a `1px` `--color-gold` rule for editorial section kickers.
- Replace decorative icons with crisp monochrome SVGs marked `aria-hidden="true"`.
- Maintain `>= 44x44px` hit targets on all mobile controls, slider dots, checkboxes, and icon buttons.

### Don't
- **Never** place `bg-accent/10 rounded-full` micro-pill badges above every section or page heading.
- **Never** use emojis (`👗`, `📱`, `💎`, `🚚`, `👋`, `🔍`, `💝`) as UI icons, empty-state illustrations, or auth headers.
- **Never** apply `transition-all`, 3D mouse-tilt (`data-tilt`), blurred background blobs (`blur-3xl`), or infinite pulsing rings (`.pulse-ring`).
- **Never** crop `logo-gold-transparent.png` with `object-cover` inside a square box.
- **Never** stack 3 competing full-width buttons inside a narrow mobile product card.

---

# 8. Responsive Behavior

- **`375px` (Mobile)**: 2-column product & category grids (`gap-3.5`), collapsible mobile drawer (`Escape` + link-close), full-width sticky inquiry bar on Favorites, zero horizontal overflow.
- **`768px` (Tablet `md`)**: Split 12-column hero (`7` copy / `5` portrait image), 2–3 column grids, sticky product detail image column.
- **`1024px–1440px` (Desktop `lg`–`xl`)**: Inline header navigation + expandable search input, 4-column product catalog grid (`gap-6`), generous editorial margins.

---

# 9. Agent Prompt Guide

When building or modifying Django templates in this repository:
1. Read `DESIGN.md` and `static/css/input.css` first; never invent arbitrary Tailwind colors that bypass `--color-primary`, `--color-secondary`, `--color-accent`, `--color-gold`, `--color-background`, and `--color-surface`.
2. Use logical RTL/LTR utilities (`ps-*`, `pe-*`, `start-*`, `end-*`, `border-s-*`, `text-start`) exclusively.
3. Add `min-w-0` to flex/grid text wrappers, `tabular-nums` to all numeric/currency output, and explicit `width`/`height` to every `<img>`.
4. Run `npm run build`, `uv run python manage.py test`, and verify both `1440x900` and `375x812` viewports via `playwright-cli` before completing UI work.
