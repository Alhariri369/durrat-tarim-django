"""Integration tests for Django Admin CRUD, image uploads, and storage failure handling."""

import tempfile
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch

import requests
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from catalog.admin import IMAGE_UPLOAD_ERROR_MESSAGE
from catalog.models import Category, FeaturedProduct, Product, StoreSettings
from support.models import Ticket

User = get_user_model()


def _make_image_file(
    name="sample.png",
    size=(200, 200),
    fmt="PNG",
    content_type="image/png",
    color=(90, 130, 180),
):
    """Create a real in-memory Pillow image wrapped in SimpleUploadedFile."""
    buf = BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=content_type)


def _make_http_error(status_code):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.text = f'{{"message": "Error {status_code}"}}'
    return requests.HTTPError(f"{status_code} Error", response=resp)


def _inline_management_data(prefix="children", total=0, initial=0):
    return {
        f"{prefix}-TOTAL_FORMS": str(total),
        f"{prefix}-INITIAL_FORMS": str(initial),
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }


class _AdminTestBase(TestCase):
    """Base class with superuser login and isolated temporary media storage."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._temp_dir = tempfile.TemporaryDirectory()
        cls._storage_override = override_settings(
            MEDIA_ROOT=cls._temp_dir.name,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                },
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
                },
            },
        )
        cls._storage_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._storage_override.disable()
        cls._temp_dir.cleanup()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.admin_user = User.objects.create_superuser(
            email="admin@example.com",
            password="StrongPassword123!",
            full_name="Admin User",
        )
        self.client.force_login(self.admin_user)

    def _category_post_data(self, **overrides):
        data = {
            "parent": "",
            "name_ar": "تصنيف اختباري",
            "name_en": "Test Category",
            "slug": "test-category",
            "is_active": "on",
            "display_order": "0",
            **_inline_management_data("children"),
        }
        data.update(overrides)
        return data

    def _product_post_data(self, category_id, **overrides):
        data = {
            "name_ar": "منتج اختباري",
            "name_en": "Test Product",
            "slug": "test-product",
            "category": str(category_id),
            "price_sar": "125.00",
            "description_ar": "وصف المنتج",
            "description_en": "Product description",
            "is_active": "on",
        }
        data.update(overrides)
        return data


class CategoryAdminTests(_AdminTestBase):
    def test_add_root_category_with_valid_image(self):
        url = reverse("admin:catalog_category_add")
        data = self._category_post_data(
            name_ar="عطور",
            name_en="Perfumes",
            slug="perfumes",
            image=_make_image_file("perfumes.png"),
        )

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, 302)
        cat = Category.objects.get(slug="perfumes")
        self.assertIsNone(cat.parent)
        self.assertTrue(cat.image.name.startswith("categorys/"))
        self.assertTrue(default_storage.exists(cat.image.name))

    @override_settings(
        IMAGEKIT_PRIVATE_KEY="private_test_key",
        IMAGEKIT_URL_ENDPOINT="https://ik.imagekit.io/demo",
        STORAGES={
            "default": {"BACKEND": "catalog.imagekit_storage.ImageKitStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        },
    )
    @patch("catalog.imagekit_storage.requests.post")
    def test_add_root_category_with_mocked_imagekit_storage(self, mock_post):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "fileId": "ik_1",
            "name": "ik_cat.png",
            "filePath": "/categorys/ik_cat.png",
        }
        mock_post.return_value = mock_resp

        url = reverse("admin:catalog_category_add")
        data = self._category_post_data(
            name_ar="بخور",
            name_en="Incense",
            slug="incense",
            image=_make_image_file("incense.png"),
        )

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, 302)
        cat = Category.objects.get(slug="incense")
        self.assertEqual(cat.image.name, "categorys/ik_cat.png")
        mock_post.assert_called_once()

    def test_add_child_category_under_empty_parent(self):
        parent = Category.objects.create(
            name_ar="ملابس",
            name_en="Clothing",
            slug="clothing",
            image=_make_image_file("parent.png"),
        )
        url = reverse("admin:catalog_category_add")
        data = self._category_post_data(
            parent=str(parent.pk),
            name_ar="ثياب رجالية",
            name_en="Menswear",
            slug="menswear",
            image=_make_image_file("child.png"),
        )

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, 302)
        child = Category.objects.get(slug="menswear")
        self.assertEqual(child.parent_id, parent.pk)

    def test_block_adding_child_under_product_holding_parent(self):
        parent = Category.objects.create(
            name_ar="عسل",
            name_en="Honey",
            slug="honey",
            image=_make_image_file("honey.png"),
        )
        Product.objects.create(
            name_ar="عسل سدر",
            slug="sidr-honey",
            category=parent,
            price_sar=Decimal("150.00"),
            image=_make_image_file("sidr.png"),
        )

        url = reverse("admin:catalog_category_add")
        data = self._category_post_data(
            parent=str(parent.pk),
            name_ar="عسل فرعي",
            name_en="Sub Honey",
            slug="sub-honey",
            image=_make_image_file("sub-honey.png"),
        )

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, 200)
        self.assertIn("parent", resp.context["adminform"].form.errors)
        self.assertFalse(Category.objects.filter(slug="sub-honey").exists())

    def test_reject_invalid_images_on_add(self):
        url = reverse("admin:catalog_category_add")
        invalid_cases = [
            (
                "tiny",
                _make_image_file("tiny.png", size=(50, 50)),
                "أبعاد الصورة صغيرة جداً",
            ),
            (
                "bad-ext",
                _make_image_file(
                    "anim.gif", fmt="GIF", content_type="image/gif"
                ),
                "صيغة الملف غير مدعومة",
            ),
            (
                "corrupt",
                SimpleUploadedFile(
                    "broken.png", b"not-a-valid-png", content_type="image/png"
                ),
                None,  # Pillow / Django ImageField rejects corrupt image bytes
            ),
        ]

        for slug_suffix, bad_file, expected_snippet in invalid_cases:
            with self.subTest(case=slug_suffix):
                before_count = Category.objects.count()
                data = self._category_post_data(
                    name_ar=f"تصنيف {slug_suffix}",
                    slug=f"invalid-{slug_suffix}",
                    image=bad_file,
                )
                resp = self.client.post(url, data)

                self.assertEqual(resp.status_code, 200)
                form = resp.context["adminform"].form
                self.assertIn("image", form.errors)
                if expected_snippet:
                    self.assertIn(expected_snippet, " ".join(form.errors["image"]))
                self.assertEqual(Category.objects.count(), before_count)

    def test_reject_invalid_image_on_edit_keeps_existing_row_intact(self):
        cat = Category.objects.create(
            name_ar="أقمشة",
            name_en="Fabrics",
            slug="fabrics",
            image=_make_image_file("fabrics.png"),
        )
        original_image_name = cat.image.name

        url = reverse("admin:catalog_category_change", args=[cat.pk])
        data = self._category_post_data(
            name_ar="أقمشة محدثة",
            name_en="Fabrics Updated",
            slug="fabrics",
            image=_make_image_file("small.png", size=(40, 40)),
        )

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, 200)
        form = resp.context["adminform"].form
        self.assertIn("image", form.errors)
        self.assertIn("أبعاد الصورة صغيرة جداً", " ".join(form.errors["image"]))
        cat.refresh_from_db()
        self.assertEqual(cat.name_ar, "أقمشة")
        self.assertEqual(cat.image.name, original_image_name)
        self.assertTrue(default_storage.exists(original_image_name))

    def test_edit_replace_image_cleans_up_old_unreferenced_image(self):
        cat = Category.objects.create(
            name_ar="إكسسوارات",
            name_en="Accessories",
            slug="accessories",
            image=_make_image_file("old.png", color=(200, 50, 50)),
        )
        old_image_name = cat.image.name
        self.assertTrue(default_storage.exists(old_image_name))

        url = reverse("admin:catalog_category_change", args=[cat.pk])
        data = self._category_post_data(
            name_ar="إكسسوارات فاخرة",
            name_en="Luxury Accessories",
            slug="accessories",
            image=_make_image_file("new.png", color=(50, 200, 50)),
        )

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, 302)
        cat.refresh_from_db()
        self.assertEqual(cat.name_ar, "إكسسوارات فاخرة")
        self.assertNotEqual(cat.image.name, old_image_name)
        self.assertTrue(default_storage.exists(cat.image.name))
        self.assertFalse(default_storage.exists(old_image_name))

    def test_delete_single_category_cleans_up_image(self):
        cat = Category.objects.create(
            name_ar="مؤقت",
            slug="temp-cat",
            image=_make_image_file("temp.png"),
        )
        image_name = cat.image.name
        self.assertTrue(default_storage.exists(image_name))

        url = reverse("admin:catalog_category_delete", args=[cat.pk])
        resp = self.client.post(url, {"post": "yes"})

        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Category.objects.filter(pk=cat.pk).exists())
        self.assertFalse(default_storage.exists(image_name))

    def test_bulk_delete_categories_cleans_up_images(self):
        cat1 = Category.objects.create(
            name_ar="حذف ١",
            slug="bulk-del-1",
            image=_make_image_file("bulk1.png"),
        )
        cat2 = Category.objects.create(
            name_ar="حذف ٢",
            slug="bulk-del-2",
            image=_make_image_file("bulk2.png"),
        )
        img1, img2 = cat1.image.name, cat2.image.name
        self.assertTrue(default_storage.exists(img1))
        self.assertTrue(default_storage.exists(img2))

        url = reverse("admin:catalog_category_changelist")
        resp = self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": [str(cat1.pk), str(cat2.pk)],
                "post": "yes",
            },
        )

        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Category.objects.filter(pk__in=[cat1.pk, cat2.pk]).exists())
        self.assertFalse(default_storage.exists(img1))
        self.assertFalse(default_storage.exists(img2))


class ProductAdminTests(_AdminTestBase):
    def setUp(self):
        super().setUp()
        self.root_cat = Category.objects.create(
            name_ar="قسم رئيسي",
            name_en="Main",
            slug="main",
            image=_make_image_file("root.png"),
        )
        self.leaf_cat = Category.objects.create(
            parent=self.root_cat,
            name_ar="قسم فرعي نهائي",
            name_en="Leaf",
            slug="leaf",
            image=_make_image_file("leaf.png"),
        )

    def test_add_product_on_leaf_category_with_valid_image(self):
        url = reverse("admin:catalog_product_add")
        data = self._product_post_data(
            self.leaf_cat.pk,
            name_ar="عطر عود",
            name_en="Oud Perfume",
            slug="oud-perfume",
            image=_make_image_file("oud.png"),
        )

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, 302)
        prod = Product.objects.get(slug="oud-perfume")
        self.assertEqual(prod.category_id, self.leaf_cat.pk)
        self.assertTrue(prod.image.name.startswith("products/"))
        self.assertTrue(default_storage.exists(prod.image.name))

    def test_block_adding_product_on_non_leaf_category(self):
        url = reverse("admin:catalog_product_add")
        data = self._product_post_data(
            self.root_cat.pk,
            name_ar="منتج في أب",
            slug="parent-product",
            image=_make_image_file("p.png"),
        )

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, 200)
        self.assertIn("category", resp.context["adminform"].form.errors)
        self.assertFalse(Product.objects.filter(slug="parent-product").exists())

    def test_reject_invalid_image_on_product_add(self):
        url = reverse("admin:catalog_product_add")
        data = self._product_post_data(
            self.leaf_cat.pk,
            name_ar="منتج بصورة صغيرة",
            slug="tiny-product",
            image=_make_image_file("tiny.png", size=(60, 60)),
        )

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, 200)
        form = resp.context["adminform"].form
        self.assertIn("image", form.errors)
        self.assertIn("أبعاد الصورة صغيرة جداً", " ".join(form.errors["image"]))
        self.assertFalse(Product.objects.filter(slug="tiny-product").exists())

    def test_reject_invalid_image_on_product_edit(self):
        prod = Product.objects.create(
            name_ar="شال تريمي",
            slug="tarim-shawl",
            category=self.leaf_cat,
            price_sar=Decimal("95.00"),
            image=_make_image_file("shawl.png"),
        )
        original_image_name = prod.image.name

        url = reverse("admin:catalog_product_change", args=[prod.pk])
        data = self._product_post_data(
            self.leaf_cat.pk,
            name_ar="شال تريمي معدل",
            slug="tarim-shawl",
            price_sar="110.00",
            image=_make_image_file("bad.gif", fmt="GIF", content_type="image/gif"),
        )

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, 200)
        form = resp.context["adminform"].form
        self.assertIn("image", form.errors)
        self.assertIn("صيغة الملف غير مدعومة", " ".join(form.errors["image"]))
        prod.refresh_from_db()
        self.assertEqual(prod.name_ar, "شال تريمي")
        self.assertEqual(prod.image.name, original_image_name)

    def test_edit_replace_product_image_cleans_up_old_image(self):
        prod = Product.objects.create(
            name_ar="دهن عود",
            slug="oud-oil",
            category=self.leaf_cat,
            price_sar=Decimal("250.00"),
            image=_make_image_file("old-oil.png", color=(180, 120, 40)),
        )
        old_image_name = prod.image.name
        self.assertTrue(default_storage.exists(old_image_name))

        url = reverse("admin:catalog_product_change", args=[prod.pk])
        data = self._product_post_data(
            self.leaf_cat.pk,
            name_ar="دهن عود معتق",
            slug="oud-oil",
            price_sar="280.00",
            image=_make_image_file("new-oil.png", color=(40, 120, 180)),
        )

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, 302)
        prod.refresh_from_db()
        self.assertEqual(prod.name_ar, "دهن عود معتق")
        self.assertEqual(prod.price_sar, Decimal("280.00"))
        self.assertNotEqual(prod.image.name, old_image_name)
        self.assertTrue(default_storage.exists(prod.image.name))
        self.assertFalse(default_storage.exists(old_image_name))

    def test_delete_single_product_cleans_up_image(self):
        prod = Product.objects.create(
            name_ar="منتج للحذف",
            slug="del-prod",
            category=self.leaf_cat,
            price_sar=Decimal("50.00"),
            image=_make_image_file("del-prod.png"),
        )
        image_name = prod.image.name
        self.assertTrue(default_storage.exists(image_name))

        url = reverse("admin:catalog_product_delete", args=[prod.pk])
        resp = self.client.post(url, {"post": "yes"})

        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Product.objects.filter(pk=prod.pk).exists())
        self.assertFalse(default_storage.exists(image_name))

    def test_bulk_delete_products_cleans_up_images(self):
        p1 = Product.objects.create(
            name_ar="حذف جماعي ١",
            slug="bulk-prod-1",
            category=self.leaf_cat,
            price_sar=Decimal("40.00"),
            image=_make_image_file("bp1.png"),
        )
        p2 = Product.objects.create(
            name_ar="حذف جماعي ٢",
            slug="bulk-prod-2",
            category=self.leaf_cat,
            price_sar=Decimal("60.00"),
            image=_make_image_file("bp2.png"),
        )
        img1, img2 = p1.image.name, p2.image.name

        url = reverse("admin:catalog_product_changelist")
        resp = self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": [str(p1.pk), str(p2.pk)],
                "post": "yes",
            },
        )

        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Product.objects.filter(pk__in=[p1.pk, p2.pk]).exists())
        self.assertFalse(default_storage.exists(img1))
        self.assertFalse(default_storage.exists(img2))


class StorageFailureInjectionAdminTests(_AdminTestBase):
    """Verify Admin never returns HTTP 500 when storage upload fails."""

    def setUp(self):
        super().setUp()
        self.leaf_cat = Category.objects.create(
            name_ar="تصنيف جاهز",
            name_en="Ready",
            slug="ready-cat",
            image=_make_image_file("ready.png"),
        )
        self.existing_product = Product.objects.create(
            name_ar="منتج قائم",
            name_en="Existing",
            slug="existing-prod",
            category=self.leaf_cat,
            price_sar=Decimal("80.00"),
            image=_make_image_file("existing.png"),
        )

    def _failure_exceptions(self):
        return [
            ("http_403", _make_http_error(403)),
            ("http_500", _make_http_error(500)),
            ("timeout", requests.Timeout("Upload timed out")),
        ]

    def _assert_graceful_failure_response(self, resp, expected_url):
        self.assertNotEqual(resp.status_code, 500)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], expected_url)

        followed = self.client.get(resp["Location"])
        self.assertEqual(followed.status_code, 200)
        msg_list = [str(m) for m in get_messages(followed.wsgi_request)]
        self.assertIn(IMAGE_UPLOAD_ERROR_MESSAGE, msg_list)
        self.assertContains(followed, IMAGE_UPLOAD_ERROR_MESSAGE)

    def test_category_add_handles_storage_failures_without_500_or_orphan_row(self):
        url = reverse("admin:catalog_category_add")
        for label, exc in self._failure_exceptions():
            with self.subTest(failure=label):
                before_count = Category.objects.count()
                data = self._category_post_data(
                    name_ar=f"فشل {label}",
                    slug=f"fail-cat-{label}",
                    image=_make_image_file(f"fail-{label}.png"),
                )
                with patch(
                    "django.core.files.storage.FileSystemStorage._save",
                    side_effect=exc,
                ):
                    resp = self.client.post(url, data)

                self._assert_graceful_failure_response(resp, url)
                self.assertEqual(Category.objects.count(), before_count)
                self.assertFalse(
                    Category.objects.filter(slug=f"fail-cat-{label}").exists()
                )

    def test_category_edit_handles_storage_failures_without_modifying_row(self):
        cat = Category.objects.create(
            name_ar="تصنيف للتعديل",
            slug="edit-fail-cat",
            image=_make_image_file("orig-cat.png"),
        )
        orig_image = cat.image.name
        url = reverse("admin:catalog_category_change", args=[cat.pk])

        for label, exc in self._failure_exceptions():
            with self.subTest(failure=label):
                data = self._category_post_data(
                    name_ar=f"اسم لن يحفظ {label}",
                    slug="edit-fail-cat",
                    image=_make_image_file(f"new-fail-{label}.png"),
                )
                with patch(
                    "django.core.files.storage.FileSystemStorage._save",
                    side_effect=exc,
                ):
                    resp = self.client.post(url, data)

                self._assert_graceful_failure_response(resp, url)
                cat.refresh_from_db()
                self.assertEqual(cat.name_ar, "تصنيف للتعديل")
                self.assertEqual(cat.image.name, orig_image)
                self.assertTrue(default_storage.exists(orig_image))

    def test_product_add_handles_storage_failures_without_500_or_orphan_row(self):
        url = reverse("admin:catalog_product_add")
        for label, exc in self._failure_exceptions():
            with self.subTest(failure=label):
                before_count = Product.objects.count()
                data = self._product_post_data(
                    self.leaf_cat.pk,
                    name_ar=f"منتج فاشل {label}",
                    slug=f"fail-prod-{label}",
                    image=_make_image_file(f"fail-prod-{label}.png"),
                )
                with patch(
                    "django.core.files.storage.FileSystemStorage._save",
                    side_effect=exc,
                ):
                    resp = self.client.post(url, data)

                self._assert_graceful_failure_response(resp, url)
                self.assertEqual(Product.objects.count(), before_count)
                self.assertFalse(
                    Product.objects.filter(slug=f"fail-prod-{label}").exists()
                )

    def test_product_edit_handles_storage_failures_without_modifying_row(self):
        orig_image = self.existing_product.image.name
        url = reverse("admin:catalog_product_change", args=[self.existing_product.pk])

        for label, exc in self._failure_exceptions():
            with self.subTest(failure=label):
                data = self._product_post_data(
                    self.leaf_cat.pk,
                    name_ar=f"تعديل فاشل {label}",
                    slug=self.existing_product.slug,
                    price_sar="999.00",
                    image=_make_image_file(f"edit-fail-{label}.png"),
                )
                with patch(
                    "django.core.files.storage.FileSystemStorage._save",
                    side_effect=exc,
                ):
                    resp = self.client.post(url, data)

                self._assert_graceful_failure_response(resp, url)
                self.existing_product.refresh_from_db()
                self.assertEqual(self.existing_product.name_ar, "منتج قائم")
                self.assertEqual(self.existing_product.price_sar, Decimal("80.00"))
                self.assertEqual(self.existing_product.image.name, orig_image)
                self.assertTrue(default_storage.exists(orig_image))

    @override_settings(
        IMAGEKIT_PRIVATE_KEY="private_test_key",
        IMAGEKIT_URL_ENDPOINT="https://ik.imagekit.io/demo",
        STORAGES={
            "default": {"BACKEND": "catalog.imagekit_storage.ImageKitStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
            },
        },
    )
    def test_imagekit_storage_403_on_category_add_never_returns_500(self):
        url = reverse("admin:catalog_category_add")
        before_count = Category.objects.count()
        data = self._category_post_data(
            name_ar="تصنيف إيمج كيت",
            slug="ik-403-cat",
            image=_make_image_file("ik403.png"),
        )

        with patch(
            "catalog.imagekit_storage.ImageKitStorage._save",
            side_effect=_make_http_error(403),
        ):
            resp = self.client.post(url, data)

        self._assert_graceful_failure_response(resp, url)
        self.assertEqual(Category.objects.count(), before_count)


class StoreSettingsAdminTests(_AdminTestBase):
    def setUp(self):
        super().setUp()
        self.settings_obj = StoreSettings.objects.create()

    def _settings_post_data(self, **overrides):
        s = self.settings_obj
        data = {
            "sar_to_yer_rate": str(s.sar_to_yer_rate),
            "local_phone": s.local_phone,
            "whatsapp_number": s.whatsapp_number,
            "address_ar": s.address_ar,
            "address_en": s.address_en,
            "light_color_primary": s.light_color_primary,
            "light_color_secondary": s.light_color_secondary,
            "light_color_accent": s.light_color_accent,
            "light_color_background": s.light_color_background,
            "light_color_surface": s.light_color_surface,
            "dark_color_primary": s.dark_color_primary,
            "dark_color_secondary": s.dark_color_secondary,
            "dark_color_accent": s.dark_color_accent,
            "dark_color_background": s.dark_color_background,
            "dark_color_surface": s.dark_color_surface,
            "contact_cooldown_seconds": str(s.contact_cooldown_seconds),
            "contact_daily_limit": str(s.contact_daily_limit),
            "analytics_retention_days": str(s.analytics_retention_days),
        }
        data.update(overrides)
        return data

    def test_singleton_blocks_add_and_delete_when_row_exists(self):
        add_resp = self.client.get(reverse("admin:catalog_storesettings_add"))
        del_resp = self.client.post(
            reverse("admin:catalog_storesettings_delete", args=[self.settings_obj.pk]),
            {"post": "yes"},
        )
        self.assertEqual(add_resp.status_code, 403)
        self.assertEqual(del_resp.status_code, 403)
        self.assertEqual(StoreSettings.objects.count(), 1)

    def test_valid_update_persists_rate_and_hex_colors(self):
        url = reverse("admin:catalog_storesettings_change", args=[self.settings_obj.pk])
        data = self._settings_post_data(
            sar_to_yer_rate="520.50",
            light_color_primary="#30669c",
            dark_color_primary="#aabbcc",
        )

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, 302)
        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.sar_to_yer_rate, Decimal("520.50"))
        self.assertEqual(self.settings_obj.light_color_primary, "#30669c")
        self.assertEqual(self.settings_obj.dark_color_primary, "#aabbcc")

    def test_invalid_hex_color_rejected_with_validation_error(self):
        url = reverse("admin:catalog_storesettings_change", args=[self.settings_obj.pk])
        original_color = self.settings_obj.light_color_primary
        data = self._settings_post_data(light_color_primary="invalid")

        resp = self.client.post(url, data)

        self.assertEqual(resp.status_code, 200)
        form = resp.context["adminform"].form
        self.assertIn("light_color_primary", form.errors)
        self.assertIn("رمز لون سداسي صحيح", " ".join(form.errors["light_color_primary"]))
        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.light_color_primary, original_color)


class FeaturedProductAdminTests(_AdminTestBase):
    def setUp(self):
        super().setUp()
        self.cat = Category.objects.create(
            name_ar="تصنيف مميز",
            slug="feat-cat",
            image=_make_image_file("feat-cat.png"),
        )
        self.product = Product.objects.create(
            name_ar="منتج مميز",
            slug="feat-prod",
            category=self.cat,
            price_sar=Decimal("200.00"),
            image=_make_image_file("feat-prod.png"),
        )

    def test_add_edit_duplicate_rejection_and_delete(self):
        add_url = reverse("admin:catalog_featuredproduct_add")
        resp = self.client.post(
            add_url,
            {
                "product": str(self.product.pk),
                "headline_ar": "عرض خاص",
                "subtitle_ar": "لفترة محدودة",
                "headline_en": "Special Offer",
                "subtitle_en": "Limited time",
                "display_order": "1",
                "is_active": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        featured = FeaturedProduct.objects.get(product=self.product)
        self.assertEqual(featured.headline_ar, "عرض خاص")

        # Duplicate OneToOne product should be rejected with HTTP 200 form error.
        dup_resp = self.client.post(
            add_url,
            {
                "product": str(self.product.pk),
                "headline_ar": "مكرر",
                "display_order": "2",
                "is_active": "on",
            },
        )
        self.assertEqual(dup_resp.status_code, 200)
        self.assertIn("product", dup_resp.context["adminform"].form.errors)
        self.assertEqual(FeaturedProduct.objects.count(), 1)

        # Edit existing featured product.
        change_url = reverse(
            "admin:catalog_featuredproduct_change", args=[featured.pk]
        )
        edit_resp = self.client.post(
            change_url,
            {
                "product": str(self.product.pk),
                "headline_ar": "عرض محدث",
                "subtitle_ar": "جديد",
                "headline_en": "Updated Offer",
                "subtitle_en": "New",
                "display_order": "5",
                "is_active": "",
            },
        )
        self.assertEqual(edit_resp.status_code, 302)
        featured.refresh_from_db()
        self.assertEqual(featured.headline_ar, "عرض محدث")
        self.assertEqual(featured.display_order, 5)
        self.assertFalse(featured.is_active)

        # Delete featured product.
        del_url = reverse("admin:catalog_featuredproduct_delete", args=[featured.pk])
        del_resp = self.client.post(del_url, {"post": "yes"})
        self.assertEqual(del_resp.status_code, 302)
        self.assertFalse(FeaturedProduct.objects.filter(pk=featured.pk).exists())


class TicketAdminTests(_AdminTestBase):
    def test_add_validation_status_transition_and_delete(self):
        add_url = reverse("admin:support_ticket_add")

        # Missing required fields returns HTTP 200 with form errors.
        bad_resp = self.client.post(
            add_url,
            {
                "name": "",
                "phone": "",
                "subject": "",
                "details": "",
                "status": Ticket.Status.NEW,
            },
        )
        self.assertEqual(bad_resp.status_code, 200)
        form = bad_resp.context["adminform"].form
        for field in ("name", "phone", "subject", "details"):
            self.assertIn(field, form.errors)
        self.assertEqual(Ticket.objects.count(), 0)

        # Valid ticket creation.
        add_resp = self.client.post(
            add_url,
            {
                "name": "أحمد",
                "phone": "783000111",
                "subject": "استفسار عن الطلب",
                "details": "هل يتوفر التوصيل إلى تريم؟",
                "status": Ticket.Status.NEW,
                "assigned_to": "",
            },
        )
        self.assertEqual(add_resp.status_code, 302)
        ticket = Ticket.objects.get(name="أحمد")
        self.assertEqual(ticket.status, Ticket.Status.NEW)

        # Transition status and assign to admin user.
        change_url = reverse("admin:support_ticket_change", args=[ticket.pk])
        edit_resp = self.client.post(
            change_url,
            {
                "name": ticket.name,
                "phone": ticket.phone,
                "subject": ticket.subject,
                "details": ticket.details,
                "status": Ticket.Status.COMPLETED,
                "assigned_to": str(self.admin_user.pk),
            },
        )
        self.assertEqual(edit_resp.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Ticket.Status.COMPLETED)
        self.assertEqual(ticket.assigned_to_id, self.admin_user.pk)

        # Delete ticket.
        del_url = reverse("admin:support_ticket_delete", args=[ticket.pk])
        del_resp = self.client.post(del_url, {"post": "yes"})
        self.assertEqual(del_resp.status_code, 302)
        self.assertFalse(Ticket.objects.filter(pk=ticket.pk).exists())
