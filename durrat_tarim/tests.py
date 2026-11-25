import io
import json
import re
import tempfile
import urllib.error
from decimal import Decimal
from html.parser import HTMLParser
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import AnonymousUser
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from catalog.models import Category, FeaturedProduct, Product, StoreSettings

from .context_processors import site_context
from .email_backend import ResendEmailBackend


@override_settings(RESEND_API_KEY="re_test", RESEND_TIMEOUT=10)
class ResendEmailBackendTests(SimpleTestCase):
    def _make_message(self, **kwargs):
        defaults = {
            "subject": "Verify your email",
            "body": "Verification message",
            "from_email": "Durrat Tarim <noreply@example.com>",
            "to": ["user@example.com"],
        }
        defaults.update(kwargs)
        return EmailMessage(**defaults)

    @patch("durrat_tarim.email_backend.urllib.request.urlopen")
    def test_send_includes_required_headers_and_payload(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"id":"email-id"}'
        urlopen.return_value = response
        backend = ResendEmailBackend()
        message = self._make_message()

        sent = backend.send_messages([message])

        self.assertEqual(sent, 1)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer re_test")
        self.assertEqual(request.get_header("User-agent"), "durrat-tarim-django/1.0")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(
            json.loads(request.data),
            {
                "from": "Durrat Tarim <noreply@example.com>",
                "to": ["user@example.com"],
                "subject": "Verify your email",
                "text": "Verification message",
            },
        )
        urlopen.assert_called_once_with(request, timeout=10)

    @patch("durrat_tarim.email_backend.urllib.request.urlopen")
    def test_send_empty_messages_returns_zero(self, urlopen):
        backend = ResendEmailBackend()

        self.assertEqual(backend.send_messages([]), 0)
        urlopen.assert_not_called()

    @override_settings(RESEND_API_KEY="")
    def test_send_requires_api_key(self):
        backend = ResendEmailBackend()
        message = self._make_message(subject="Test", body="Test")

        with self.assertRaisesMessage(ValueError, "RESEND_API_KEY is not configured"):
            backend.send_messages([message])

    @override_settings(RESEND_API_KEY="")
    def test_send_without_api_key_fail_silently_returns_zero(self):
        backend = ResendEmailBackend(fail_silently=True)
        message = self._make_message()

        self.assertEqual(backend.send_messages([message]), 0)

    @patch("durrat_tarim.email_backend.urllib.request.urlopen")
    def test_send_http_error_raises_runtime_error(self, urlopen):
        http_err = urllib.error.HTTPError(
            url=ResendEmailBackend.API_URL,
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=io.BytesIO(b'{"message":"Invalid API key"}'),
        )
        urlopen.side_effect = http_err
        backend = ResendEmailBackend(fail_silently=False)

        with self.assertRaises(RuntimeError) as ctx:
            backend.send_messages([self._make_message()])

        self.assertIn("Resend HTTP 403", str(ctx.exception))
        self.assertIn("Invalid API key", str(ctx.exception))

    @patch("durrat_tarim.email_backend.urllib.request.urlopen")
    def test_send_http_error_fail_silently_returns_zero(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            url=ResendEmailBackend.API_URL,
            code=500,
            msg="Server Error",
            hdrs=None,
            fp=io.BytesIO(b"upstream failure"),
        )
        backend = ResendEmailBackend(fail_silently=True)

        self.assertEqual(backend.send_messages([self._make_message()]), 0)

    @patch("durrat_tarim.email_backend.urllib.request.urlopen")
    def test_send_timeout_raises_runtime_error(self, urlopen):
        urlopen.side_effect = TimeoutError("timed out")
        backend = ResendEmailBackend(fail_silently=False)

        with self.assertRaises(RuntimeError) as ctx:
            backend.send_messages([self._make_message()])

        self.assertIn("Resend network error", str(ctx.exception))

    @patch("durrat_tarim.email_backend.urllib.request.urlopen")
    def test_send_timeout_fail_silently_continues_batch(self, urlopen):
        ok_resp = MagicMock()
        ok_resp.__enter__.return_value.read.return_value = b'{"id":"ok"}'
        urlopen.side_effect = [TimeoutError("timed out"), ok_resp]
        backend = ResendEmailBackend(fail_silently=True)

        sent = backend.send_messages([self._make_message(), self._make_message()])

        self.assertEqual(sent, 1)

    @patch("durrat_tarim.email_backend.urllib.request.urlopen")
    def test_send_html_and_multipart_alternatives(self, urlopen):
        ok_resp = MagicMock()
        ok_resp.__enter__.return_value.read.return_value = b'{"id":"ok"}'
        urlopen.return_value = ok_resp
        backend = ResendEmailBackend()

        html_msg = self._make_message(body="<p>Hello</p>")
        html_msg.content_subtype = "html"

        multi_msg = EmailMultiAlternatives(
            subject="Multi",
            body="Plain body",
            from_email="noreply@example.com",
            to=["user@example.com"],
        )
        multi_msg.attach_alternative("<h1>HTML body</h1>", "text/html")

        sent = backend.send_messages([html_msg, multi_msg])

        self.assertEqual(sent, 2)
        first_payload = json.loads(urlopen.call_args_list[0].args[0].data)
        second_payload = json.loads(urlopen.call_args_list[1].args[0].data)
        self.assertEqual(first_payload["html"], "<p>Hello</p>")
        self.assertNotIn("text", first_payload)
        self.assertEqual(second_payload["text"], "Plain body")
        self.assertEqual(second_payload["html"], "<h1>HTML body</h1>")


class ContextProcessorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_site_context_on_empty_database_for_anonymous_user(self):
        StoreSettings.objects.all().delete()
        Category.objects.all().delete()
        Product.objects.all().delete()

        request = self.factory.get("/")
        request.user = AnonymousUser()

        ctx = site_context(request)

        self.assertIsNotNone(ctx["site_settings"])
        self.assertIsNone(ctx["store_user"])
        self.assertFalse(ctx["is_store_authenticated"])
        self.assertFalse(ctx["is_store_admin"])
        self.assertEqual(ctx["account_action_url"], reverse("account_login"))
        self.assertEqual(ctx["account_action_label"], "تسجيل الدخول")

    def test_site_context_for_regular_and_staff_users(self):
        regular = User.objects.create_user(
            email="regular@example.com", password="secret", is_staff=False
        )
        staff = User.objects.create_user(
            email="staff@example.com", password="secret", is_staff=True
        )

        req_regular = self.factory.get("/")
        req_regular.user = regular
        ctx_regular = site_context(req_regular)
        self.assertEqual(ctx_regular["store_user"], regular)
        self.assertTrue(ctx_regular["is_store_authenticated"])
        self.assertFalse(ctx_regular["is_store_admin"])
        self.assertEqual(ctx_regular["account_action_url"], reverse("account_logout"))
        self.assertEqual(ctx_regular["account_action_label"], "تسجيل الخروج")

        req_staff = self.factory.get("/")
        req_staff.user = staff
        ctx_staff = site_context(req_staff)
        self.assertTrue(ctx_staff["is_store_authenticated"])
        self.assertTrue(ctx_staff["is_store_admin"])

    def test_home_page_renders_on_empty_database(self):
        StoreSettings.objects.all().delete()
        Category.objects.all().delete()
        Product.objects.all().delete()

        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)


class SitemapAndRobotsTests(TestCase):
    def test_sitemap_index_and_sections_on_empty_database(self):
        StoreSettings.objects.all().delete()
        Category.objects.all().delete()
        Product.objects.all().delete()

        index_resp = self.client.get("/sitemap.xml")
        self.assertEqual(index_resp.status_code, 200)
        self.assertEqual(index_resp["Content-Type"], "application/xml")
        self.assertEqual(
            index_resp["X-Robots-Tag"], "noindex, noodp, noarchive"
        )
        body = index_resp.content.decode("utf-8")
        self.assertIn("<sitemapindex", body)
        self.assertIn("http://testserver/sitemap-static.xml", body)
        self.assertIn("http://testserver/sitemap-categories.xml", body)
        self.assertIn("http://testserver/sitemap-products.xml", body)

        for section in ("static", "categories", "products"):
            resp = self.client.get(f"/sitemap-{section}.xml")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp["Content-Type"], "application/xml")
            self.assertIn("<urlset", resp.content.decode("utf-8"))

    def test_sitemap_unknown_section_and_invalid_page_return_404(self):
        self.assertEqual(self.client.get("/sitemap-nonexistent.xml").status_code, 404)
        self.assertEqual(self.client.get("/sitemap-static.xml?p=abc").status_code, 404)
        self.assertEqual(self.client.get("/sitemap-static.xml?p=999").status_code, 404)

    def test_sitemap_populated_database_includes_only_active_items_and_uses_request_host(
        self,
    ):
        StoreSettings.objects.create()
        active_cat = Category.objects.create(
            name_ar="تصنيف نشط", slug="active-cat", is_active=True
        )
        inactive_cat = Category.objects.create(
            name_ar="تصنيف مخفي", slug="inactive-cat", is_active=False
        )
        active_prod = Product.objects.create(
            name_ar="منتج نشط",
            slug="active-prod",
            category=active_cat,
            price_sar=Decimal("100.00"),
            image="products/active.png",
            is_active=True,
        )
        inactive_prod = Product.objects.create(
            name_ar="منتج مخفي",
            slug="inactive-prod",
            category=active_cat,
            price_sar=Decimal("100.00"),
            image="products/inactive.png",
            is_active=False,
        )
        hidden_cat_prod = Product.objects.create(
            name_ar="منتج بتصنيف مخفي",
            slug="hidden-cat-prod",
            category=inactive_cat,
            price_sar=Decimal("100.00"),
            image="products/hidden.png",
            is_active=True,
        )

        with override_settings(ALLOWED_HOSTS=["durrat-tarim.example.com", "testserver"]):
            cat_resp = self.client.get(
                "/sitemap-categories.xml", HTTP_HOST="durrat-tarim.example.com"
            )
            self.assertEqual(cat_resp.status_code, 200)
            cat_xml = cat_resp.content.decode("utf-8")
            self.assertIn(
                "http://durrat-tarim.example.com/products/types/active-cat/", cat_xml
            )
            self.assertNotIn("inactive-cat", cat_xml)

            prod_resp = self.client.get(
                "/sitemap-products.xml", HTTP_HOST="durrat-tarim.example.com"
            )
            self.assertEqual(prod_resp.status_code, 200)
            prod_xml = prod_resp.content.decode("utf-8")
            self.assertIn(
                f"http://durrat-tarim.example.com{reverse('product-detail', args=[active_prod.pk])}",
                prod_xml,
            )
            self.assertNotIn(
                reverse("product-detail", args=[inactive_prod.pk]), prod_xml
            )
            self.assertNotIn(
                reverse("product-detail", args=[hidden_cat_prod.pk]), prod_xml
            )

            static_resp = self.client.get(
                "/sitemap-static.xml", HTTP_HOST="durrat-tarim.example.com"
            )
            self.assertEqual(static_resp.status_code, 200)
            self.assertIn("Last-Modified", static_resp.headers)

    def test_robots_txt_rendering(self):
        response = self.client.get("/robots.txt")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")
        body = response.content.decode("utf-8")
        self.assertIn("User-agent: *", body)
        self.assertIn("Allow: /", body)
        self.assertIn("Disallow: /admin/", body)
        self.assertIn("Disallow: /auth/", body)
        self.assertIn("Disallow: /dashboard/", body)
        self.assertIn("Disallow: /favorites/", body)
        self.assertIn("Disallow: /search/", body)
        self.assertIn("Disallow: /products/search/", body)
        self.assertIn("Disallow: /products/items/*/whatsapp/", body)
        self.assertIn("Disallow: /*?q=*", body)
        self.assertNotIn("Disallow: /*?*\n", body)
        self.assertIn("Sitemap: http://testserver/sitemap.xml", body)


class _HeadSeoParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._in_title = False
        self._in_ld = False
        self._ld_chunks = []
        self.titles = []
        self.metas = []
        self.links = []
        self.json_lds = []
        self.h1_count = 0

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)
        if tag == "title":
            self._in_title = True
            self.titles.append("")
        elif tag == "meta":
            self.metas.append(attr_map)
        elif tag == "link":
            self.links.append(attr_map)
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "script" and attr_map.get("type") == "application/ld+json":
            self._in_ld = True
            self._ld_chunks = []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_ld:
            self._in_ld = False
            self.json_lds.append("".join(self._ld_chunks).strip())

    def handle_data(self, data):
        if self._in_title:
            self.titles[-1] += data
        elif self._in_ld:
            self._ld_chunks.append(data)


def _parse_seo(html_bytes):
    parser = _HeadSeoParser()
    parser.feed(html_bytes.decode("utf-8"))
    return parser


def _tiny_image(name="seo.jpg"):
    from PIL import Image

    img = Image.new("RGB", (60, 80), color=(107, 76, 140))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


class SeoMetadataAndSchemaTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temp_media = tempfile.TemporaryDirectory()
        cls._storage_override = override_settings(
            MEDIA_ROOT=cls._temp_media.name,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                    "OPTIONS": {"location": cls._temp_media.name},
                },
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
                },
            },
        )
        cls._storage_override.enable()
        try:
            super().setUpClass()
        except Exception:
            cls._storage_override.disable()
            cls._temp_media.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            super().tearDownClass()
        finally:
            cls._storage_override.disable()
            cls._temp_media.cleanup()

    @classmethod
    def setUpTestData(cls):
        StoreSettings.get_current()
        cls.category = Category.objects.create(
            name_ar="قطع عرائسية",
            slug="bridal-pieces",
            image=_tiny_image("cat.jpg"),
        )
        cls.products = []
        for idx in range(14):
            prod = Product.objects.create(
                name_ar=f"قطعة عرائسية مطرزة {idx}",
                slug=f"bridal-piece-{idx}",
                description_ar=f"وصف قطعة رقم {idx} من درة تريم.",
                category=cls.category,
                price_sar=Decimal("250.00"),
                image=_tiny_image(f"prod-{idx}.jpg"),
            )
            cls.products.append(prod)
        FeaturedProduct.objects.create(product=cls.products[0], display_order=1)
        FeaturedProduct.objects.create(product=cls.products[1], display_order=2)

    def _canonical(self, parsed):
        return next(
            (link["href"] for link in parsed.links if link.get("rel") == "canonical"),
            None,
        )

    def _meta(self, parsed, name):
        return next(
            (m.get("content") for m in parsed.metas if m.get("name") == name),
            None,
        )

    def test_titles_are_single_line_without_duplication(self):
        routes = [
            reverse("home"),
            reverse("product-list"),
            f"{reverse('product-list')}?page=2",
            reverse("product-types"),
            reverse("product-type", args=[self.category.slug]),
            f"{reverse('product-type', args=[self.category.slug])}?page=2",
            reverse("product-detail", args=[self.products[0].pk]),
            f"{reverse('product-search')}?q=عرائسية",
            reverse("contact"),
            reverse("account_login"),
            reverse("account_signup"),
            "/this-page-does-not-exist-404/",
        ]
        for url in routes:
            with self.subTest(url=url):
                resp = self.client.get(url, HTTP_HOST="durrattarim.com")
                parsed = _parse_seo(resp.content)
                self.assertEqual(len(parsed.titles), 1)
                title = parsed.titles[0]
                self.assertNotIn("\n", title)
                self.assertEqual(title.count("درة تريم"), 1)
                self.assertTrue(self._meta(parsed, "description"))

        prod_title = _parse_seo(
            self.client.get(
                reverse("product-detail", args=[self.products[0].pk]),
                HTTP_HOST="durrattarim.com",
            ).content
        ).titles[0]
        self.assertEqual(prod_title.count(self.products[0].name_ar), 1)

        cat_title = _parse_seo(
            self.client.get(
                reverse("product-type", args=[self.category.slug]),
                HTTP_HOST="durrattarim.com",
            ).content
        ).titles[0]
        self.assertEqual(cat_title.count(self.category.name_ar), 1)

    def test_canonical_urls_strip_tracking_and_handle_pagination(self):
        home_parsed = _parse_seo(
            self.client.get("/?utm_source=ig&fbclid=123", HTTP_HOST="durrattarim.com").content
        )
        self.assertEqual(self._canonical(home_parsed), "http://durrattarim.com/")

        p1_parsed = _parse_seo(
            self.client.get(
                f"{reverse('product-list')}?page=1&utm_medium=social",
                HTTP_HOST="durrattarim.com",
            ).content
        )
        self.assertEqual(self._canonical(p1_parsed), "http://durrattarim.com/products/")

        p2_parsed = _parse_seo(
            self.client.get(
                f"{reverse('product-list')}?page=2&utm_source=x",
                HTTP_HOST="durrattarim.com",
            ).content
        )
        self.assertEqual(
            self._canonical(p2_parsed), "http://durrattarim.com/products/?page=2"
        )

        cat_p2 = _parse_seo(
            self.client.get(
                f"{reverse('product-type', args=[self.category.slug])}?page=2",
                HTTP_HOST="durrattarim.com",
            ).content
        )
        self.assertEqual(
            self._canonical(cat_p2),
            f"http://durrattarim.com/products/types/{self.category.slug}/?page=2",
        )

        empty_search = _parse_seo(
            self.client.get(reverse("product-search"), HTTP_HOST="durrattarim.com").content
        )
        self.assertEqual(
            self._canonical(empty_search), "http://durrattarim.com/products/"
        )

    def test_vercel_app_hosts_are_blocked_while_custom_domain_is_indexable(self):
        for host in ("durrat-tarim-dev.vercel.app", "durttrim.vercel.app"):
            with self.subTest(host=host):
                resp = self.client.get("/", HTTP_HOST=host)
                self.assertEqual(resp.headers.get("X-Robots-Tag"), "noindex, nofollow")
                parsed = _parse_seo(resp.content)
                self.assertEqual(self._meta(parsed, "robots"), "noindex,nofollow")
                self.assertIsNone(self._meta(parsed, "google-site-verification"))
                robots_resp = self.client.get("/robots.txt", HTTP_HOST=host)
                self.assertEqual(
                    robots_resp.content.decode("utf-8"), "User-agent: *\nDisallow: /\n"
                )

        prod_resp = self.client.get("/", HTTP_HOST="durrattarim.com")
        self.assertNotIn("X-Robots-Tag", prod_resp.headers)
        prod_parsed = _parse_seo(prod_resp.content)
        self.assertEqual(self._meta(prod_parsed, "robots"), "index,follow")
        self.assertTrue(self._meta(prod_parsed, "google-site-verification"))

        for noindex_url in (
            reverse("account_login"),
            reverse("account_signup"),
            "/missing-route-404/",
        ):
            r = self.client.get(noindex_url, HTTP_HOST="durrattarim.com")
            self.assertEqual(
                self._meta(_parse_seo(r.content), "robots"), "noindex,nofollow"
            )

        with override_settings(ALLOW_VERCEL_APP_INDEXING=True):
            allowed_resp = self.client.get("/", HTTP_HOST="durttrim.vercel.app")
            self.assertNotIn("X-Robots-Tag", allowed_resp.headers)
            self.assertEqual(
                self._meta(_parse_seo(allowed_resp.content), "robots"), "index,follow"
            )

    def test_json_ld_schemas_parse_cleanly_with_hadhramout_local_seo(self):
        home_resp = self.client.get("/", HTTP_HOST="durrattarim.com")
        home_parsed = _parse_seo(home_resp.content)
        self.assertEqual(home_parsed.h1_count, 1)
        home_schemas = [json.loads(raw) for raw in home_parsed.json_lds]
        types = {s["@type"] for s in home_schemas}
        self.assertEqual(types, {"ClothingStore", "WebSite", "FAQPage"})
        store = next(s for s in home_schemas if s["@type"] == "ClothingStore")
        self.assertEqual(store["address"]["addressLocality"], "تريم")
        self.assertEqual(store["address"]["addressRegion"], "حضرموت")
        self.assertEqual(store["address"]["addressCountry"], "YE")
        areas = {a["name"] for a in store["areaServed"]}
        self.assertEqual(areas, {"تريم", "سيئون", "وادي حضرموت", "اليمن"})

        for url, expected_types in (
            (reverse("product-list"), {"ClothingStore", "WebSite", "CollectionPage", "BreadcrumbList"}),
            (
                reverse("product-type", args=[self.category.slug]),
                {"ClothingStore", "WebSite", "CollectionPage", "BreadcrumbList"},
            ),
            (
                reverse("product-detail", args=[self.products[0].pk]),
                {"ClothingStore", "WebSite", "Product", "BreadcrumbList"},
            ),
            (reverse("contact"), {"ClothingStore", "WebSite", "BreadcrumbList"}),
        ):
            with self.subTest(url=url):
                parsed = _parse_seo(self.client.get(url, HTTP_HOST="durrattarim.com").content)
                schemas = [json.loads(raw) for raw in parsed.json_lds]
                self.assertEqual({s["@type"] for s in schemas}, expected_types)
                if "Product" in expected_types:
                    prod_schema = next(s for s in schemas if s["@type"] == "Product")
                    self.assertEqual(prod_schema["brand"]["name"], "درة تريم")

    def test_whatsapp_nofollow_sitemap_products_and_favicon(self):
        detail_html = self.client.get(
            reverse("product-detail", args=[self.products[0].pk]),
            HTTP_HOST="durrattarim.com",
        ).content.decode("utf-8")
        wa_href = reverse("product-whatsapp", args=[self.products[0].pk])
        self.assertRegex(
            detail_html,
            rf'<a[^>]*href="{re.escape(wa_href)}"[^>]*rel="nofollow"',
        )

        static_sitemap = self.client.get(
            "/sitemap-static.xml", HTTP_HOST="durrattarim.com"
        ).content.decode("utf-8")
        self.assertIn("http://durrattarim.com/products/", static_sitemap)

        favicon_resp = self.client.get("/favicon.ico", HTTP_HOST="durrattarim.com")
        self.assertEqual(favicon_resp.status_code, 301)
        self.assertIn("favicon.png", favicon_resp["Location"])
