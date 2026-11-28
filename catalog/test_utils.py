"""Unit tests for catalog.currency and catalog.whatsapp utilities."""

from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from django.core.cache import cache
from django.test import RequestFactory, TestCase

from catalog.currency import (
    _get_rate,
    format_sar,
    format_yer,
    invalidate_rate_cache,
    sar_to_yer,
    sar_to_yer_display,
)
from catalog.models import Category, Product, StoreSettings
from catalog.whatsapp import (
    MAX_FAVORITES_PER_MESSAGE,
    MAX_WHATSAPP_MESSAGE_LENGTH,
    WHATSAPP_NUMBER,
    canonical_product_url,
    favorites_message,
    product_message,
    whatsapp_url,
)


class CurrencyUtilsTests(TestCase):
    def setUp(self):
        cache.clear()
        StoreSettings.objects.all().delete()
        self.settings = StoreSettings.objects.create(sar_to_yer_rate=Decimal("410.00"))

    def tearDown(self):
        cache.clear()

    def test_get_rate_caches_and_invalidates(self):
        self.assertEqual(_get_rate(), Decimal("410.00"))
        self.assertEqual(cache.get("sar_to_yer_rate"), Decimal("410.00"))

        # Direct DB update does not bypass cache until invalidated.
        StoreSettings.objects.filter(pk=self.settings.pk).update(
            sar_to_yer_rate=Decimal("500.00")
        )
        StoreSettings.invalidate_cache()
        self.assertEqual(_get_rate(), Decimal("410.00"))

        invalidate_rate_cache()
        self.assertEqual(_get_rate(), Decimal("500.00"))

    def test_get_rate_creates_default_settings_when_empty(self):
        StoreSettings.objects.all().delete()
        StoreSettings.invalidate_cache()
        invalidate_rate_cache()

        rate = _get_rate()
        self.assertEqual(rate, Decimal(410))
        self.assertEqual(StoreSettings.objects.count(), 1)

    def test_sar_to_yer_and_rounding(self):
        StoreSettings.objects.filter(pk=self.settings.pk).update(
            sar_to_yer_rate=Decimal("410.50")
        )
        StoreSettings.invalidate_cache()
        invalidate_rate_cache()

        self.assertEqual(sar_to_yer(Decimal("1.00")), Decimal("410.5000"))
        # ROUND_HALF_UP: 410.5 -> 411
        self.assertEqual(sar_to_yer_display(Decimal("1.00")), 411)
        # 0.01 * 410.50 = 4.105 -> 4
        self.assertEqual(sar_to_yer_display(Decimal("0.01")), 4)

    def test_format_sar_and_format_yer(self):
        self.assertEqual(format_sar(Decimal(0)), "0.00 ر.س")
        self.assertEqual(format_sar(Decimal("1250.5")), "1,250.50 ر.س")
        self.assertEqual(format_yer(Decimal("100.00")), "41,000 ر.ي")
        self.assertEqual(format_yer(Decimal("0.00")), "0 ر.ي")


class WhatsAppUtilsTests(TestCase):
    def setUp(self):
        cache.clear()
        StoreSettings.objects.all().delete()
        StoreSettings.objects.create(sar_to_yer_rate=Decimal("400.00"))
        self.factory = RequestFactory()
        self.request = self.factory.get("/", HTTP_HOST="localhost")
        self.category = Category.objects.create(
            name_ar="عطورات", slug="perfumes", image="categorys/p.png"
        )
        self.product = Product.objects.create(
            name_ar="عود تريم الفاخر",
            slug="tarim-oud",
            category=self.category,
            price_sar=Decimal("120.00"),
            image="products/p1.png",
        )

    def tearDown(self):
        cache.clear()

    def test_canonical_product_url(self):
        url = canonical_product_url(self.request, self.product)
        self.assertEqual(
            url, f"http://localhost/products/items/{self.product.pk}/"
        )

    def test_product_message_contains_arabic_details_and_url(self):
        msg = product_message(self.request, self.product)
        self.assertIn("السلام عليكم", msg)
        self.assertIn("عود تريم الفاخر", msg)
        self.assertIn("120.00 ر.س", msg)
        self.assertIn("48,000 ر.ي", msg)
        self.assertIn(canonical_product_url(self.request, self.product), msg)

    def test_favorites_message_empty_list(self):
        msg, included = favorites_message(self.request, [])
        self.assertEqual(included, 0)
        self.assertIn("السلام عليكم", msg)

    def test_favorites_message_caps_at_max_items(self):
        products = [
            Product.objects.create(
                name_ar=f"منتج {i}",
                slug=f"prod-{i}",
                category=self.category,
                price_sar=Decimal("10.00"),
                image=f"products/p{i}.png",
            )
            for i in range(MAX_FAVORITES_PER_MESSAGE + 5)
        ]
        msg, included = favorites_message(self.request, products)
        self.assertEqual(included, MAX_FAVORITES_PER_MESSAGE)
        self.assertIn(f"{MAX_FAVORITES_PER_MESSAGE}. منتج {MAX_FAVORITES_PER_MESSAGE - 1}", msg)
        self.assertNotIn(f"منتج {MAX_FAVORITES_PER_MESSAGE}", msg)

    def test_favorites_message_truncates_at_max_length(self):
        long_name = "عطر " * 45  # ~180 chars
        products = [
            Product.objects.create(
                name_ar=f"{long_name}{i}",
                slug=f"long-prod-{i}",
                category=self.category,
                price_sar=Decimal("50.00"),
                image=f"products/lp{i}.png",
            )
            for i in range(25)
        ]
        msg, included = favorites_message(self.request, products)
        self.assertLessEqual(len(msg), MAX_WHATSAPP_MESSAGE_LENGTH)
        self.assertGreater(included, 0)
        self.assertLess(included, MAX_FAVORITES_PER_MESSAGE)

    def test_whatsapp_url_encodes_arabic_message(self):
        message = "السلام عليكم\nعود تريم الفاخر"
        url = whatsapp_url(message)
        parsed = urlparse(url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "wa.me")
        self.assertEqual(parsed.path, f"/{WHATSAPP_NUMBER}")
        self.assertEqual(parse_qs(parsed.query)["text"], [message])
