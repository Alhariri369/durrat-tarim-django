import io
import json
import urllib.error
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import AnonymousUser
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from catalog.models import Category, Product, StoreSettings

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
        self.assertIn("Disallow: /*?*", body)
        self.assertIn("Sitemap: http://testserver/sitemap.xml", body)
