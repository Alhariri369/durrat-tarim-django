import re
from html.parser import HTMLParser
from pathlib import Path

from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts.models import User

from .admin import StoreSettingsAdmin
from .models import StoreSettings, _validate_hex_color

LIGHT_COLOR_DEFAULTS = {
    "light_color_primary": "#6b4c8c",
    "light_color_secondary": "#1f1629",
    "light_color_accent": "#a974c4",
    "light_color_background": "#f7f3fa",
    "light_color_surface": "#ffffff",
}

DARK_COLOR_DEFAULTS = {
    "dark_color_primary": "#c9a7eb",
    "dark_color_secondary": "#efe8f7",
    "dark_color_accent": "#d8a7f0",
    "dark_color_background": "#140d1c",
    "dark_color_surface": "#1e1429",
}

ALL_COLOR_DEFAULTS = {**LIGHT_COLOR_DEFAULTS, **DARK_COLOR_DEFAULTS}


class _TagCollector(HTMLParser):
    """Lightweight HTML parser that records attributes for selected tags."""

    def __init__(self, target_tags):
        super().__init__()
        self.target_tags = set(target_tags)
        self.tags = []

    def handle_starttag(self, tag, attrs):
        if tag in self.target_tags:
            self.tags.append((tag, dict(attrs)))


def _collect_tags(html, *tag_names):
    parser = _TagCollector(tag_names)
    parser.feed(html)
    return parser.tags


# ---------------------------------------------------------------------------
# 1. StoreSettings color model tests
# ---------------------------------------------------------------------------


class StoreSettingsColorModelTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_default_values_for_all_ten_color_fields(self):
        store_settings = StoreSettings.get_current()
        for field_name, expected_hex in ALL_COLOR_DEFAULTS.items():
            with self.subTest(field=field_name):
                self.assertEqual(getattr(store_settings, field_name), expected_hex)

    def test_color_fields_document_css_token_in_help_text(self):
        expected_tokens = {
            "light_color_primary": "--color-primary",
            "light_color_secondary": "--color-secondary",
            "light_color_accent": "--color-accent",
            "light_color_background": "--color-background",
            "light_color_surface": "--color-surface",
            "dark_color_primary": "--color-primary",
            "dark_color_secondary": "--color-secondary",
            "dark_color_accent": "--color-accent",
            "dark_color_background": "--color-background",
            "dark_color_surface": "--color-surface",
        }
        for field_name, token in expected_tokens.items():
            with self.subTest(field=field_name):
                field = StoreSettings._meta.get_field(field_name)
                self.assertIn(token, field.help_text)

    def test_validate_hex_color_accepts_valid_six_digit_hex(self):
        valid_values = [
            "#000000",
            "#ffffff",
            "#FFFFFF",
            "#30669c",
            "#e0801f",
            "#39f2f9",
            "#0aB1c2",
        ]
        for value in valid_values:
            with self.subTest(value=value):
                _validate_hex_color(value)

    def test_validate_hex_color_rejects_invalid_formats(self):
        invalid_values = [
            "red",
            "#fff",
            "#12345g",
            "123456",
            "#12345",
            "#1234567",
            "",
            "rgb(0,0,0)",
        ]
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    _validate_hex_color(value)

    def test_model_full_clean_rejects_invalid_color(self):
        store_settings = StoreSettings.get_current()
        store_settings.light_color_primary = "red"
        with self.assertRaises(ValidationError):
            store_settings.full_clean()


# ---------------------------------------------------------------------------
# 2. StoreSettingsAdmin tests
# ---------------------------------------------------------------------------


class StoreSettingsAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            email="theme-admin@example.com",
            password="Theme-Admin-Password-9421",
            full_name="Theme Admin",
        )

    def setUp(self):
        cache.clear()
        self.store_settings = StoreSettings.get_current()
        self.model_admin = StoreSettingsAdmin(StoreSettings, AdminSite())

    def tearDown(self):
        cache.clear()

    def _flattened_fieldset_fields(self):
        fields = []
        for _title, options in self.model_admin.fieldsets:
            for item in options.get("fields", ()):
                if isinstance(item, (tuple, list)):
                    fields.extend(item)
                else:
                    fields.append(item)
        return fields

    def test_fieldsets_include_all_ten_color_fields_and_previews(self):
        fieldset_fields = set(self._flattened_fieldset_fields())
        for field_name in ALL_COLOR_DEFAULTS:
            self.assertIn(field_name, fieldset_fields)
        self.assertIn("light_color_preview", fieldset_fields)
        self.assertIn("dark_color_preview", fieldset_fields)
        self.assertIn("light_color_preview", self.model_admin.readonly_fields)
        self.assertIn("dark_color_preview", self.model_admin.readonly_fields)

    def test_swatch_previews_render_all_hex_values(self):
        light_html = str(self.model_admin.light_color_preview(self.store_settings))
        dark_html = str(self.model_admin.dark_color_preview(self.store_settings))

        for hex_value in LIGHT_COLOR_DEFAULTS.values():
            self.assertIn(hex_value, light_html)
        for hex_value in DARK_COLOR_DEFAULTS.values():
            self.assertIn(hex_value, dark_html)

        self.assertEqual(self.model_admin.light_color_preview(None), "-")
        self.assertEqual(self.model_admin.dark_color_preview(None), "-")

    def test_admin_change_form_renders_color_pickers_with_hex_text_inputs(self):
        self.client.force_login(self.superuser)
        change_url = reverse(
            "admin:catalog_storesettings_change", args=[self.store_settings.pk]
        )
        response = self.client.get(change_url)
        self.assertEqual(response.status_code, 200)

        html = response.content.decode("utf-8")
        inputs = [attrs for _tag, attrs in _collect_tags(html, "input")]

        color_inputs = [
            attrs for attrs in inputs if (attrs.get("type") or "").lower() == "color"
        ]
        self.assertGreaterEqual(
            len(color_inputs),
            len(ALL_COLOR_DEFAULTS),
            "Expected an <input type='color'> picker for each of the 10 color fields.",
        )

        text_inputs_by_name = {
            attrs.get("name"): attrs
            for attrs in inputs
            if attrs.get("name") in ALL_COLOR_DEFAULTS
            and (attrs.get("type") or "text").lower() == "text"
        }
        for field_name, default_hex in ALL_COLOR_DEFAULTS.items():
            with self.subTest(field=field_name):
                self.assertIn(
                    field_name,
                    text_inputs_by_name,
                    f"Missing hex text input for {field_name} in admin form.",
                )
                self.assertEqual(
                    (text_inputs_by_name[field_name].get("value") or "").lower(),
                    default_hex.lower(),
                )

    def test_saving_via_admin_invalidates_store_settings_cache(self):
        # Prime the cache first.
        cached = StoreSettings.get_current()
        self.assertEqual(cached.light_color_primary, "#6b4c8c")

        self.client.force_login(self.superuser)
        change_url = reverse(
            "admin:catalog_storesettings_change", args=[self.store_settings.pk]
        )
        payload = {
            "sar_to_yer_rate": str(self.store_settings.sar_to_yer_rate),
            "local_phone": self.store_settings.local_phone,
            "whatsapp_number": self.store_settings.whatsapp_number,
            "address_ar": self.store_settings.address_ar,
            "address_en": self.store_settings.address_en,
            **ALL_COLOR_DEFAULTS,
            "light_color_primary": "#123456",
            "contact_cooldown_seconds": str(
                self.store_settings.contact_cooldown_seconds
            ),
            "contact_daily_limit": str(self.store_settings.contact_daily_limit),
            "analytics_retention_days": str(
                self.store_settings.analytics_retention_days
            ),
            "_save": "Save",
        }
        response = self.client.post(change_url, payload)
        self.assertEqual(response.status_code, 302)

        # Cache must have been invalidated so get_current() returns the saved value.
        refreshed = StoreSettings.get_current()
        self.assertEqual(refreshed.light_color_primary, "#123456")


# ---------------------------------------------------------------------------
# 3. Rendered template tests (GET /)
# ---------------------------------------------------------------------------


class ThemeTemplateRenderTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store_settings = StoreSettings.get_current()

    def tearDown(self):
        cache.clear()

    def test_theme_variables_outputs_live_colors_and_updates_after_cache_invalidation(
        self,
    ):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")

        self.assertIn("--color-primary: #6b4c8c;", html)
        self.assertIn("--color-secondary: #1f1629;", html)
        self.assertIn("--color-accent: #a974c4;", html)
        self.assertIn("--color-background: #f7f3fa;", html)
        self.assertIn("--color-surface: #ffffff;", html)

        # Edit colors in DB and invalidate cache; rendered HTML must reflect updates.
        self.store_settings.light_color_primary = "#1a2b3c"
        self.store_settings.light_color_accent = "#c45d12"
        self.store_settings.light_color_surface = "#faf8f5"
        self.store_settings.save()
        StoreSettings.invalidate_cache()

        updated_response = self.client.get(reverse("home"))
        self.assertEqual(updated_response.status_code, 200)
        updated_html = updated_response.content.decode("utf-8")

        self.assertIn("--color-primary: #1a2b3c;", updated_html)
        self.assertIn("--color-accent: #c45d12;", updated_html)
        self.assertIn("--color-surface: #faf8f5;", updated_html)

    def test_meta_theme_color_is_light_only_and_uses_light_color_background(self):
        self.store_settings.light_color_background = "#f1e9e2"
        self.store_settings.save()
        StoreSettings.invalidate_cache()

        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")

        theme_color_metas = [
            attrs
            for _tag, attrs in _collect_tags(html, "meta")
            if attrs.get("name") == "theme-color"
        ]
        self.assertEqual(
            len(theme_color_metas),
            1,
            "Expected a single light-only <meta name='theme-color'> tag.",
        )
        self.assertEqual(theme_color_metas[0].get("content"), "#f1e9e2")
        self.assertNotIn("media", theme_color_metas[0])
        self.assertNotIn('media="(prefers-color-scheme: dark)"', html)

    def test_dark_mode_ui_and_script_are_cleanly_disabled(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")

        self.assertNotIn('id="theme-toggle"', html)
        self.assertNotIn('id="theme-toggle-mobile"', html)

        script_srcs = [
            attrs.get("src") or ""
            for _tag, attrs in _collect_tags(html, "script")
            if attrs.get("src")
        ]
        self.assertFalse(
            any("js/theme.js" in src for src in script_srcs),
            f"Unexpected active theme.js script tag found: {script_srcs}",
        )

    def test_social_links_render_instagram_gradient_and_brand_tokens(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")

        anchors = [attrs for _tag, attrs in _collect_tags(html, "a")]

        instagram_links = [
            attrs for attrs in anchors if "instagram.com" in (attrs.get("href") or "")
        ]
        self.assertTrue(instagram_links, "Expected Instagram link in rendered home page.")
        self.assertTrue(
            any(
                "bg-instagram-gradient" in (attrs.get("class") or "")
                for attrs in instagram_links
            ),
            "Expected prominent Instagram link styled with 'bg-instagram-gradient'.",
        )

        whatsapp_links = [
            attrs for attrs in anchors if "wa.me" in (attrs.get("href") or "")
        ]
        self.assertTrue(whatsapp_links, "Expected WhatsApp link in rendered home page.")
        self.assertTrue(
            any("whatsapp" in (attrs.get("class") or "") for attrs in whatsapp_links),
            "Expected WhatsApp link styled with '--color-whatsapp' token class.",
        )

        tiktok_links = [
            attrs for attrs in anchors if "tiktok.com" in (attrs.get("href") or "")
        ]
        self.assertTrue(tiktok_links, "Expected TikTok link in rendered home page.")
        self.assertTrue(
            any("tiktok" in (attrs.get("class") or "") for attrs in tiktok_links),
            "Expected TikTok link styled with '--color-tiktok' token class.",
        )


# ---------------------------------------------------------------------------
# 4. Static & template hygiene tests
# ---------------------------------------------------------------------------


class ThemeStaticHygieneTests(SimpleTestCase):
    ARBITRARY_HEX_CLASS_RE = re.compile(
        r"\b(?:bg|text|border|from|to|via)-\[#[0-9a-fA-F]{3,8}\]"
    )
    HEX_LITERAL_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
    RGB_LITERAL_RE = re.compile(r"\brgba?\s*\(", re.IGNORECASE)

    @property
    def base_dir(self):
        return Path(settings.BASE_DIR)

    def test_templates_contain_no_arbitrary_hex_color_classes(self):
        templates_dir = self.base_dir / "templates"
        html_files = sorted(templates_dir.rglob("*.html"))
        self.assertTrue(html_files, "Expected HTML templates under templates/.")

        offenders = []
        for path in html_files:
            content = path.read_text(encoding="utf-8")
            matches = self.ARBITRARY_HEX_CLASS_RE.findall(content)
            if matches:
                rel = path.relative_to(self.base_dir)
                offenders.append(f"{rel}: {matches}")

        self.assertEqual(
            offenders,
            [],
            f"Found arbitrary hex color classes in templates: {offenders}",
        )

    def test_header_template_contains_no_from_black(self):
        header_path = self.base_dir / "templates" / "partials" / "header.html"
        content = header_path.read_text(encoding="utf-8")
        self.assertNotRegex(
            content,
            r"\bfrom-black\b",
            "header.html should use 'from-secondary' instead of 'from-black'.",
        )

    def test_animations_css_contains_no_hardcoded_hex_or_rgb_colors(self):
        animations_path = self.base_dir / "static" / "css" / "animations.css"
        content = animations_path.read_text(encoding="utf-8")

        hex_matches = self.HEX_LITERAL_RE.findall(content)
        rgb_matches = self.RGB_LITERAL_RE.findall(content)

        self.assertEqual(
            hex_matches,
            [],
            f"Found hardcoded hex colors in animations.css: {hex_matches}",
        )
        self.assertEqual(
            rgb_matches,
            [],
            f"Found hardcoded rgb()/rgba() colors in animations.css: {rgb_matches}",
        )

    def test_compiled_output_css_has_all_required_tokens_and_no_docs_leaks(self):
        output_css_path = self.base_dir / "static" / "css" / "output.css"
        self.assertTrue(
            output_css_path.exists(), "Expected compiled static/css/output.css."
        )
        css = output_css_path.read_text(encoding="utf-8")

        required_tokens = [
            "--color-primary",
            "--color-secondary",
            "--color-accent",
            "--color-background",
            "--color-surface",
            "--color-border",
            "--color-focus",
            "--color-whatsapp",
            "--color-instagram",
            "--color-tiktok",
            "--font-tajawal",
        ]
        for token in required_tokens:
            with self.subTest(token=token):
                self.assertIn(
                    token,
                    css,
                    f"Required @theme token '{token}' missing from static/css/output.css.",
                )

        # Ensure Tailwind v4 source(none) prevented docs/ markdown junk like `.bg-[#...]`
        self.assertNotRegex(
            css,
            r"\\\[\\?#\\?\.\\?\.\\?\.\\?\]",
            "Junk docs utility (.bg-[#...]) leaked into static/css/output.css.",
        )
        self.assertNotIn("bg-[#...]", css)
