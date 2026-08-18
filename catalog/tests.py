import decimal
import io
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from allauth.account.models import EmailAddress
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .currency import sar_to_yer, sar_to_yer_display
from .image_storage import _validate_image
from .models import Category, Favorite, FeaturedProduct, Product, StoreSettings
from .views import PRODUCTS_PER_PAGE, _public_products
from .whatsapp import MAX_FAVORITES_PER_MESSAGE, product_whatsapp_clicked


def _fake_image(name="test.jpg", width=100, height=100):
    """Generate a minimal valid JPEG of given dimensions for testing."""
    from PIL import Image

    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return SimpleUploadedFile(
        name=name,
        content=buf.getvalue(),
        content_type="image/jpeg",
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class CategoryModelTests(TestCase):
    def test_requires_name_ar_and_image(self):
        cat = Category(name_ar="عبايات", slug="abayat", image=_fake_image())
        cat.full_clean()
        cat.save()
        self.assertEqual(Category.objects.count(), 1)
        self.assertEqual(str(cat), "عبايات")

    def test_name_en_is_optional(self):
        cat = Category(name_ar="فساتين", slug="fasateen", image=_fake_image())
        cat.full_clean()
        cat.save()
        self.assertEqual(cat.name_en, "")


class ProductModelTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name_ar="عبايات", slug="abayat", image=_fake_image()
        )

    def test_requires_category_name_ar_price_image(self):
        prod = Product(
            name_ar="عباية ناعم",
            slug="abaya-naem",
            category=self.category,
            price_sar=decimal.Decimal("120.00"),
            image=_fake_image(),
        )
        prod.full_clean()
        prod.save()
        self.assertEqual(Product.objects.count(), 1)

    def test_price_sar_non_negative_constraint(self):
        from django.db import IntegrityError

        prod = Product(
            name_ar="سلعة",
            slug="negative-test",
            category=self.category,
            price_sar=decimal.Decimal("-1.00"),
            image=_fake_image(),
        )
        with self.assertRaises((IntegrityError, Exception)):
            prod.save()

    def test_category_is_required(self):
        from django.core.exceptions import ValidationError

        prod = Product(
            name_ar="بدون تصنيف",
            slug="no-cat",
            price_sar=decimal.Decimal("50"),
            image=_fake_image(),
        )
        with self.assertRaises(ValidationError):
            prod.full_clean()


class FeaturedProductModelTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name_ar="عبايات", slug="abayat", image=_fake_image()
        )
        self.product = Product.objects.create(
            name_ar="عباية",
            slug="abaya-1",
            category=self.category,
            price_sar=decimal.Decimal("100"),
            image=_fake_image(),
        )

    def test_featured_product_creation(self):
        fp = FeaturedProduct(
            product=self.product,
            headline_ar="خصم خاص",
        )
        fp.full_clean()
        fp.save()
        self.assertEqual(FeaturedProduct.objects.count(), 1)
        self.assertIn("مميز", str(fp))


class StoreSettingsTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_singleton_returns_same_row(self):
        s1 = StoreSettings.get_current()
        s2 = StoreSettings.get_current()
        self.assertEqual(s1.pk, s2.pk)

    def test_default_sar_to_yer_rate(self):
        s = StoreSettings.get_current()
        self.assertEqual(s.sar_to_yer_rate, decimal.Decimal("410"))

    def test_cannot_create_second_row(self):
        StoreSettings.get_current()
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            s2 = StoreSettings()
            s2.save()

    def test_invalidate_cache(self):
        s = StoreSettings.get_current()
        s.sar_to_yer_rate = decimal.Decimal("420")
        s.save()
        StoreSettings.invalidate_cache()
        s2 = StoreSettings.get_current()
        self.assertEqual(s2.sar_to_yer_rate, decimal.Decimal("420"))

    def test_cached_context_processor_rate(self):
        s = StoreSettings.get_current()
        s.sar_to_yer_rate = decimal.Decimal("415")
        s.save()
        StoreSettings.invalidate_cache()
        from .currency import invalidate_rate_cache

        invalidate_rate_cache()
        self.assertEqual(sar_to_yer(decimal.Decimal("1")), decimal.Decimal("415"))


# ---------------------------------------------------------------------------
# Currency tests
# ---------------------------------------------------------------------------


class CurrencyTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_sar_to_yer_conversion(self):
        s = StoreSettings.get_current()
        s.sar_to_yer_rate = decimal.Decimal("410")
        s.save()
        StoreSettings.invalidate_cache()
        from .currency import invalidate_rate_cache

        invalidate_rate_cache()
        self.assertEqual(sar_to_yer(decimal.Decimal("10")), decimal.Decimal("4100"))

    def test_sar_to_yer_display_rounds_whole(self):
        s = StoreSettings.get_current()
        s.sar_to_yer_rate = decimal.Decimal("410")
        s.save()
        StoreSettings.invalidate_cache()
        from .currency import invalidate_rate_cache

        invalidate_rate_cache()
        self.assertEqual(sar_to_yer_display(decimal.Decimal("10.5")), 4305)


# ---------------------------------------------------------------------------
# Image validation tests
# ---------------------------------------------------------------------------


class ImageValidationTests(TestCase):
    def test_valid_standard_image(self):
        img = _fake_image("ok.jpg")
        _validate_image(img)  # should not raise

    def test_rejects_oversized_file(self):
        from django.core.exceptions import ValidationError

        img = SimpleUploadedFile(
            "big.jpg", b"\xff" * (6 * 1024 * 1024), content_type="image/jpeg"
        )
        with self.assertRaises(ValidationError):
            _validate_image(img)

    def test_rejects_invalid_extension(self):
        from django.core.exceptions import ValidationError

        img = SimpleUploadedFile("doc.txt", b"hello", content_type="text/plain")
        with self.assertRaises(ValidationError):
            _validate_image(img)

    def test_rejects_non_image_content(self):
        from django.core.exceptions import ValidationError

        img = SimpleUploadedFile("fake.jpg", b"not an image", content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            _validate_image(img)


# ---------------------------------------------------------------------------
# View tests (updated to new field names)
# ---------------------------------------------------------------------------


class CatalogViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name_ar="عبايات", slug="abayat", image=_fake_image("cat.jpg")
        )
        cls.product = Product.objects.create(
            name_ar="عباية ناعم",
            slug="abaya-naem",
            category=cls.category,
            price_sar=decimal.Decimal("120.00"),
            description_ar="وصف",
            image=_fake_image("prod.jpg"),
        )

    def test_home_renders(self):
        home = self.client.get(reverse("home"))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "عباية ناعم")

    def test_search_renders(self):
        search = self.client.get(reverse("product-search"), {"product_desc": "عباية"})
        self.assertEqual(search.status_code, 200)
        self.assertContains(search, "عباية")

    def test_product_detail_renders(self):
        response = self.client.get(
            reverse("product-detail", kwargs={"pk": self.product.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "عباية")


# ---------------------------------------------------------------------------
# StoreSettings context processor tests
# ---------------------------------------------------------------------------


class StoreSettingsContextTests(TestCase):
    def test_context_processor_returns_settings(self):
        response = self.client.get(reverse("home"))
        self.assertIn("site_settings", response.context)
        self.assertIn("is_store_authenticated", response.context)


class StorefrontMilestoneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name_ar="عبايات", slug="abayat-public", image=_fake_image("public-cat.jpg")
        )
        cls.inactive_category = Category.objects.create(
            name_ar="مخفي",
            slug="hidden-cat",
            image=_fake_image("hidden-cat.jpg"),
            is_active=False,
        )
        cls.old_product = Product.objects.create(
            name_ar="القديم",
            slug="old-product",
            category=cls.category,
            price_sar=decimal.Decimal("100.00"),
            image=_fake_image("old.jpg"),
            created_at=timezone.now() - timedelta(days=2),
        )
        cls.new_product = Product.objects.create(
            name_ar="الجديد",
            slug="new-product",
            category=cls.category,
            price_sar=decimal.Decimal("120.00"),
            image=_fake_image("new.jpg"),
            created_at=timezone.now() - timedelta(days=1),
        )
        cls.inactive_product = Product.objects.create(
            name_ar="غير نشط",
            slug="inactive-product",
            category=cls.category,
            price_sar=decimal.Decimal("50.00"),
            image=_fake_image("inactive.jpg"),
            is_active=False,
        )
        cls.hidden_category_product = Product.objects.create(
            name_ar="ضمن تصنيف مخفي",
            slug="hidden-category-product",
            category=cls.inactive_category,
            price_sar=decimal.Decimal("70.00"),
            image=_fake_image("hidden-product.jpg"),
        )
        FeaturedProduct.objects.create(product=cls.new_product, display_order=1)
        FeaturedProduct.objects.create(product=cls.inactive_product, display_order=0)

    def test_home_has_usable_featured_data_latest_order_and_categories(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item.product for item in response.context["featured"]], [self.new_product]
        )
        self.assertEqual(
            response.context["products"][:2], [self.new_product, self.old_product]
        )
        self.assertContains(response, self.category.image.url)
        self.assertContains(response, "data-featured-slider")
        self.assertContains(response, "120.00 ر.س")
        self.assertContains(response, "49,200 ر.ي")
        self.assertNotContains(response, "/cart")
        self.assertNotContains(response, "إضافة إلى السلة")

    def test_search_preserves_query_and_excludes_all_inactive_content(self):
        response = self.client.get(reverse("product-search"), {"q": "الجديد"})
        self.assertContains(response, 'value="الجديد"')
        self.assertContains(response, "الجديد")
        all_products = self.client.get(reverse("product-search"))
        self.assertNotContains(all_products, "غير نشط")
        self.assertNotContains(all_products, "ضمن تصنيف مخفي")

    def test_search_uses_paginator_and_preserves_query_parameters(self):
        for index in range(PRODUCTS_PER_PAGE + 1):
            Product.objects.create(
                name_ar=f"منتج بحث {index}",
                slug=f"search-product-{index}",
                category=self.category,
                price_sar=1,
                image=_fake_image(f"search-{index}.jpg"),
            )
        response = self.client.get(reverse("product-search"), {"q": "منتج", "page": 2})
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertContains(response, "q=%D9%85%D9%86%D8%AA%D8%AC")

    def test_category_routes_use_active_stable_slugs(self):
        self.assertEqual(
            self.client.get(
                reverse("product-type", args=[self.category.slug])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse("product-type", args=[self.inactive_category.slug])
            ).status_code,
            404,
        )

    def test_inactive_products_are_not_public(self):
        for product in (self.inactive_product, self.hidden_category_product):
            self.assertEqual(
                self.client.get(
                    reverse("product-detail", args=[product.pk])
                ).status_code,
                404,
            )
            self.assertEqual(
                self.client.get(
                    reverse("product-whatsapp", args=[product.pk])
                ).status_code,
                404,
            )

    def test_product_whatsapp_redirect_has_number_message_prices_and_canonical_url(
        self,
    ):
        received = []
        receiver = lambda sender, **kwargs: received.append(kwargs["product"].pk)
        product_whatsapp_clicked.connect(receiver)
        try:
            response = self.client.get(
                reverse("product-whatsapp", args=[self.new_product.pk])
            )
        finally:
            product_whatsapp_clicked.disconnect(receiver)
        parsed = urlparse(response.url)
        message = parse_qs(parsed.query)["text"][0]
        self.assertEqual(response.status_code, 302)
        self.assertEqual(parsed.netloc, "wa.me")
        self.assertEqual(parsed.path, "/967783278181")
        self.assertIn("الجديد", message)
        self.assertIn("120.00 ر.س", message)
        self.assertIn("49,200 ر.ي", message)
        self.assertIn(reverse("product-detail", args=[self.new_product.pk]), message)
        self.assertEqual(received, [self.new_product.pk])


class FavoriteMilestoneTests(TestCase):
    password = "Zebra-Planet-8462"

    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name_ar="فساتين",
            slug="favorite-dresses",
            image=_fake_image("favorite-cat.jpg"),
        )
        cls.product = Product.objects.create(
            name_ar="فستان مفضل",
            slug="favorite-dress",
            category=cls.category,
            price_sar=decimal.Decimal("10.00"),
            image=_fake_image("favorite.jpg"),
        )
        cls.inactive_product = Product.objects.create(
            name_ar="مفضل مخفي",
            slug="hidden-favorite",
            category=cls.category,
            price_sar=decimal.Decimal("5.00"),
            image=_fake_image("hidden-favorite.jpg"),
            is_active=False,
        )
        cls.user = User.objects.create_user(
            email="verified@example.com", password=cls.password
        )
        EmailAddress.objects.create(
            user=cls.user, email=cls.user.email, verified=True, primary=True
        )
        cls.other_user = User.objects.create_user(
            email="other@example.com", password=cls.password
        )
        EmailAddress.objects.create(
            user=cls.other_user, email=cls.other_user.email, verified=True, primary=True
        )
        cls.unverified_user = User.objects.create_user(
            email="unverified@example.com", password=cls.password
        )
        EmailAddress.objects.create(
            user=cls.unverified_user,
            email=cls.unverified_user.email,
            verified=False,
            primary=True,
        )

    def test_uniqueness_constraint_blocks_duplicate_favorites(self):
        Favorite.objects.create(user=self.user, product=self.product)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Favorite.objects.create(user=self.user, product=self.product)

    def test_favorite_requires_post_csrf_authentication_and_verification(self):
        url = reverse("favorite-add", args=[self.product.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        anonymous = self.client.post(
            url, {"next": reverse("product-detail", args=[self.product.pk])}
        )
        self.assertIn(reverse("account_login"), anonymous.url)
        self.client.force_login(self.unverified_user)
        unverified = self.client.post(
            url, {"next": reverse("product-detail", args=[self.product.pk])}
        )
        self.assertIn(reverse("account_email_verification_sent"), unverified.url)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(url).status_code, 403)

    def test_add_and_remove_are_idempotent_and_owned(self):
        self.client.force_login(self.user)
        add_url = reverse("favorite-add", args=[self.product.pk])
        for _ in range(2):
            self.client.post(add_url)
        self.assertEqual(
            Favorite.objects.filter(user=self.user, product=self.product).count(), 1
        )
        Favorite.objects.create(user=self.other_user, product=self.product)
        remove_url = reverse("favorite-remove", args=[self.product.pk])
        for _ in range(2):
            self.client.post(remove_url)
        self.assertFalse(
            Favorite.objects.filter(user=self.user, product=self.product).exists()
        )
        self.assertTrue(
            Favorite.objects.filter(user=self.other_user, product=self.product).exists()
        )

    def test_inactive_products_cannot_be_added_and_are_hidden_from_list(self):
        Favorite.objects.create(user=self.user, product=self.inactive_product)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("favorite-add", args=[self.inactive_product.pk])
        )
        self.assertEqual(response.status_code, 404)
        favorites_page = self.client.get(reverse("favorites"))
        self.assertNotContains(favorites_page, self.inactive_product.name_ar)

    def test_favorites_are_paginated_and_deletion_is_safe(self):
        self.client.force_login(self.user)
        Favorite.objects.create(user=self.user, product=self.product)
        for index in range(PRODUCTS_PER_PAGE):
            product = Product.objects.create(
                name_ar=f"مفضل {index}",
                slug=f"favorite-page-{index}",
                category=self.category,
                price_sar=2,
                image=_fake_image(f"favorite-page-{index}.jpg"),
            )
            Favorite.objects.create(user=self.user, product=product)
        response = self.client.get(reverse("favorites"), {"page": 2})
        self.assertEqual(response.context["page_obj"].number, 2)
        self.product.delete()
        self.assertFalse(
            Favorite.objects.filter(user=self.user, product_id=self.product.pk).exists()
        )

    def test_favorite_counts_are_annotated_without_n_plus_one_queries(self):
        Favorite.objects.create(user=self.user, product=self.product)
        with self.assertNumQueries(1):
            products = list(_public_products(self.user).filter(pk=self.product.pk))
            self.assertEqual(products[0].favorite_count, 1)
            self.assertTrue(products[0].is_favorite)

    def test_selected_favorites_whatsapp_is_owned_bounded_and_current(self):
        Favorite.objects.create(user=self.user, product=self.product)
        Favorite.objects.create(user=self.other_user, product=self.inactive_product)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("favorites-whatsapp"),
            {"products": [self.product.pk, self.inactive_product.pk]},
        )
        parsed = urlparse(response.url)
        message = parse_qs(parsed.query)["text"][0]
        self.assertEqual(parsed.path, "/967783278181")
        self.assertIn(self.product.name_ar, message)
        self.assertNotIn(self.inactive_product.name_ar, message)
        self.assertIn("10.00 ر.س", message)
        self.assertIn(reverse("product-detail", args=[self.product.pk]), message)
        self.assertLessEqual(len(message), 3500)
        self.assertEqual(MAX_FAVORITES_PER_MESSAGE, 20)
