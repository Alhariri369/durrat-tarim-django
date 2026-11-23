import decimal
from html.parser import HTMLParser
import io
from pathlib import Path
import tempfile

from django.conf import settings
from django.contrib.admin import SimpleListFilter
from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from accounts.models import User

from .admin import CategoryAdmin, ProductAdmin, _image_preview
from .models import Category, FeaturedProduct, Product


def _fake_image(name="test.jpg", width=100, height=100):
    """Generate a minimal valid JPEG in memory for testing."""
    from PIL import Image

    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return SimpleUploadedFile(
        name=name,
        content=buf.getvalue(),
        content_type="image/jpeg",
    )


class _ImgCollector(HTMLParser):
    """Lightweight HTML parser that records attributes of every <img> tag."""

    def __init__(self):
        super().__init__()
        self.images = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.images.append(dict(attrs))


def _collect_images(html):
    parser = _ImgCollector()
    parser.feed(html)
    return parser.images


class _LocalMediaTestCase(TestCase):
    """Base TestCase that redirects default media storage to a temp directory
    so tests never touch live ImageKit or leave files in uploads/."""

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

    def setUp(self):
        super().setUp()
        cache.clear()

    def tearDown(self):
        cache.clear()
        super().tearDown()


# ---------------------------------------------------------------------------
# 1. Model & hierarchy invariant tests
# ---------------------------------------------------------------------------


class CategoryHierarchyModelTests(_LocalMediaTestCase):
    def setUp(self):
        super().setUp()
        self.root = Category.objects.create(
            name_ar="ملابس نسائية",
            name_en="Women Wear",
            slug="women-wear",
            image=_fake_image("root.jpg"),
            display_order=1,
        )
        self.sub = Category.objects.create(
            name_ar="عبايات",
            name_en="Abayas",
            slug="abayas",
            parent=self.root,
            image=_fake_image("sub.jpg"),
            display_order=1,
        )
        self.leaf = Category.objects.create(
            name_ar="عبايات سوداء",
            name_en="Black Abayas",
            slug="black-abayas",
            parent=self.sub,
            image=_fake_image("leaf.jpg"),
            display_order=1,
        )
        self.product = Product.objects.create(
            name_ar="عباية كريب سوداء",
            name_en="Black Crepe Abaya",
            slug="black-crepe-abaya",
            category=self.leaf,
            price_sar=decimal.Decimal("180.00"),
            image=_fake_image("prod.jpg"),
        )

    def test_three_level_chain_properties_and_helpers(self):
        # is_root
        self.assertTrue(self.root.is_root)
        self.assertFalse(self.sub.is_root)
        self.assertFalse(self.leaf.is_root)

        # is_leaf (persisted and unsaved)
        self.assertFalse(self.root.is_leaf)
        self.assertFalse(self.sub.is_leaf)
        self.assertTrue(self.leaf.is_leaf)
        unsaved = Category(name_ar="مؤقت", slug="temp-unsaved")
        self.assertTrue(unsaved.is_leaf)

        # depth
        self.assertEqual(self.root.depth, 0)
        self.assertEqual(self.sub.depth, 1)
        self.assertEqual(self.leaf.depth, 2)

        # get_ancestors()
        self.assertEqual(self.root.get_ancestors(), [])
        self.assertEqual(self.sub.get_ancestors(), [self.root])
        self.assertEqual(self.leaf.get_ancestors(), [self.root, self.sub])

        # get_path_categories()
        self.assertEqual(self.root.get_path_categories(), [self.root])
        self.assertEqual(self.sub.get_path_categories(), [self.root, self.sub])
        self.assertEqual(
            self.leaf.get_path_categories(), [self.root, self.sub, self.leaf]
        )

        # full_path
        self.assertEqual(self.root.full_path, "ملابس نسائية")
        self.assertEqual(self.sub.full_path, "ملابس نسائية / عبايات")
        self.assertEqual(
            self.leaf.full_path, "ملابس نسائية / عبايات / عبايات سوداء"
        )

        # leaf_queryset()
        leaf_ids = set(Category.leaf_queryset().values_list("id", flat=True))
        self.assertEqual(leaf_ids, {self.leaf.id})

        # tree_ordered_categories() preserves DFS order across sibling branches
        other_root = Category.objects.create(
            name_ar="إكسسوارات",
            slug="accessories",
            image=_fake_image("other-root.jpg"),
            display_order=2,
        )
        other_child = Category.objects.create(
            name_ar="حقائب",
            slug="bags",
            parent=other_root,
            image=_fake_image("bags.jpg"),
            display_order=1,
        )
        ordered = list(Category.tree_ordered_categories())
        self.assertEqual(
            [c.id for c in ordered],
            [self.root.id, self.sub.id, self.leaf.id, other_root.id, other_child.id],
        )

    def test_active_category_ids_respects_entire_ancestor_chain(self):
        self.assertEqual(
            Category.active_category_ids(),
            {self.root.id, self.sub.id, self.leaf.id},
        )

        # Deactivating intermediate node hides itself and its leaf descendant.
        self.sub.is_active = False
        self.sub.save()
        self.assertEqual(Category.active_category_ids(), {self.root.id})

        # Re-activating sub and deactivating root hides the whole subtree.
        self.sub.is_active = True
        self.sub.save()
        self.root.is_active = False
        self.root.save()
        self.assertEqual(Category.active_category_ids(), set())

    def test_assigning_product_to_non_leaf_category_rejected(self):
        for non_leaf, label in ((self.root, "root"), (self.sub, "intermediate")):
            with self.subTest(parent_level=label):
                candidate = Product(
                    name_ar=f"منتج غير صالح {label}",
                    slug=f"invalid-prod-{label}",
                    category=non_leaf,
                    price_sar=decimal.Decimal("99.00"),
                    image=_fake_image(f"bad-{label}.jpg"),
                )
                with self.assertRaises(ValidationError):
                    candidate.full_clean()
                with self.assertRaises(ValidationError):
                    candidate.save()
                with self.assertRaises(ValidationError):
                    Product.objects.create(
                        name_ar=f"منتج مرفوض {label}",
                        slug=f"invalid-create-{label}",
                        category=non_leaf,
                        price_sar=decimal.Decimal("99.00"),
                        image=_fake_image(f"bad-create-{label}.jpg"),
                    )

        # Moving an existing product to a non-leaf parent is also blocked.
        self.product.category = self.sub
        with self.assertRaises(ValidationError):
            self.product.full_clean()
        with self.assertRaises(ValidationError):
            self.product.save()

    def test_creating_or_moving_child_category_under_category_with_products_rejected(
        self,
    ):
        # Creating a new child under self.leaf (which has self.product) must fail.
        new_child = Category(
            name_ar="تصنيف فرعي غير مسموح",
            slug="illegal-child",
            parent=self.leaf,
            image=_fake_image("illegal-child.jpg"),
        )
        with self.assertRaises(ValidationError):
            new_child.full_clean()
        with self.assertRaises(ValidationError):
            new_child.save()
        with self.assertRaises(ValidationError):
            Category.objects.create(
                name_ar="تصنيف فرعي غير مسموح 2",
                slug="illegal-child-2",
                parent=self.leaf,
                image=_fake_image("illegal-child-2.jpg"),
            )

        # Moving an existing category under self.leaf must also fail.
        standalone = Category.objects.create(
            name_ar="تصنيف مستقل",
            slug="standalone-cat",
            image=_fake_image("standalone.jpg"),
        )
        standalone.parent = self.leaf
        with self.assertRaises(ValidationError):
            standalone.full_clean()
        with self.assertRaises(ValidationError):
            standalone.save()

    def test_self_parenting_and_indirect_cycles_rejected(self):
        # Self-parenting
        self.root.parent = self.root
        with self.assertRaises(ValidationError):
            self.root.full_clean()
        with self.assertRaises(ValidationError):
            self.root.save()
        self.root.refresh_from_db()

        # Indirect cycle: A (cat_a) -> B (cat_b) -> C (cat_c), then A.parent = C
        cat_a = Category.objects.create(
            name_ar="أ", slug="cycle-a", image=_fake_image("a.jpg")
        )
        cat_b = Category.objects.create(
            name_ar="ب", slug="cycle-b", parent=cat_a, image=_fake_image("b.jpg")
        )
        cat_c = Category.objects.create(
            name_ar="ج", slug="cycle-c", parent=cat_b, image=_fake_image("c.jpg")
        )
        cat_a.parent = cat_c
        with self.assertRaises(ValidationError):
            cat_a.full_clean()
        with self.assertRaises(ValidationError):
            cat_a.save()

    def test_protected_error_prevents_deleting_parent_with_children_or_leaf_with_products(
        self,
    ):
        with self.assertRaises(ProtectedError):
            self.root.delete()

        with self.assertRaises(ProtectedError):
            self.sub.delete()

        with self.assertRaises(ProtectedError):
            self.leaf.delete()

        # An empty leaf category (no children, no products) can be deleted cleanly.
        empty_leaf = Category.objects.create(
            name_ar="تصنيف فارغ",
            slug="empty-leaf",
            parent=self.sub,
            image=_fake_image("empty.jpg"),
        )
        empty_leaf_pk = empty_leaf.pk
        empty_leaf.delete()
        self.assertFalse(Category.objects.filter(pk=empty_leaf_pk).exists())


# ---------------------------------------------------------------------------
# 2. Admin UI & leaf-only form tests
# ---------------------------------------------------------------------------


class CategoryAndProductAdminTests(_LocalMediaTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            email="hierarchy-admin@example.com",
            password="Hierarchy-Admin-Password-7421",
            full_name="Hierarchy Admin",
        )
        cls.root = Category.objects.create(
            name_ar="أزياء",
            name_en="Fashion",
            slug="admin-fashion",
            image=_fake_image("admin-root.jpg"),
            display_order=1,
        )
        cls.sub = Category.objects.create(
            name_ar="عبايات فاخرة",
            name_en="Luxury Abayas",
            slug="admin-luxury-abayas",
            parent=cls.root,
            image=_fake_image("admin-sub.jpg"),
            display_order=1,
        )
        cls.leaf = Category.objects.create(
            name_ar="عبايات مطرزة",
            name_en="Embroidered Abayas",
            slug="admin-embroidered-abayas",
            parent=cls.sub,
            image=_fake_image("admin-leaf.jpg"),
            display_order=1,
        )
        cls.empty_leaf = Category.objects.create(
            name_ar="عبايات سادة",
            name_en="Plain Abayas",
            slug="admin-plain-abayas",
            parent=cls.sub,
            image=_fake_image("admin-empty-leaf.jpg"),
            display_order=2,
        )
        cls.other_root = Category.objects.create(
            name_ar="إكسسوارات",
            name_en="Accessories",
            slug="admin-accessories",
            image=_fake_image("admin-other-root.jpg"),
            display_order=2,
        )
        cls.product = Product.objects.create(
            name_ar="عباية تطريز ذهبي",
            name_en="Gold Embroidered Abaya",
            slug="admin-gold-abaya",
            category=cls.leaf,
            price_sar=decimal.Decimal("290.00"),
            image=_fake_image("admin-prod.jpg"),
        )

    def setUp(self):
        super().setUp()
        self.client.force_login(self.superuser)

    def _find_node_type_filter(self):
        """Locate the custom node-type SimpleListFilter registered on CategoryAdmin."""
        request = RequestFactory().get("/")
        request.user = self.superuser
        model_admin = CategoryAdmin(Category, AdminSite())
        for item in CategoryAdmin.list_filter:
            if isinstance(item, type) and issubclass(item, SimpleListFilter):
                dummy = item(request, {}, Category, model_admin)
                lookup_keys = {key for key, _label in dummy.lookups(request, model_admin)}
                if {"roots", "folders", "leaves"}.issubset(lookup_keys):
                    return item.parameter_name, lookup_keys
        return None, set()

    def test_category_changelist_renders_tree_hierarchy_and_node_type_filter(self):
        changelist_url = reverse("admin:catalog_category_changelist")
        response = self.client.get(changelist_url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")

        # Tree hierarchy display includes all levels and tree_name column.
        self.assertTrue(
            hasattr(CategoryAdmin, "tree_name"),
            "CategoryAdmin should define a tree_name display method.",
        )
        for cat in (self.root, self.sub, self.leaf, self.empty_leaf, self.other_root):
            self.assertIn(cat.name_ar, html)

        # Admin image preview includes placeholder fallback.
        preview_html = str(_image_preview(self.product))
        self.assertIn("product-placeholder.svg", preview_html)
        self.assertIn("onerror", preview_html)

        # Custom node-type filter must be registered and filter accurately.
        param_name, lookup_keys = self._find_node_type_filter()
        self.assertIsNotNone(
            param_name,
            "Expected a SimpleListFilter with roots/folders/leaves on CategoryAdmin.",
        )
        self.assertTrue({"roots", "folders", "leaves"}.issubset(lookup_keys))

        leaves_resp = self.client.get(changelist_url, {param_name: "leaves"})
        self.assertEqual(leaves_resp.status_code, 200)
        leaf_qs_ids = set(
            leaves_resp.context["cl"].queryset.values_list("pk", flat=True)
        )
        self.assertEqual(
            leaf_qs_ids, {self.leaf.pk, self.empty_leaf.pk, self.other_root.pk}
        )
        self.assertNotIn(self.root.pk, leaf_qs_ids)
        self.assertNotIn(self.sub.pk, leaf_qs_ids)

        roots_resp = self.client.get(changelist_url, {param_name: "roots"})
        self.assertEqual(roots_resp.status_code, 200)
        root_qs_ids = set(
            roots_resp.context["cl"].queryset.values_list("pk", flat=True)
        )
        self.assertEqual(root_qs_ids, {self.root.pk, self.other_root.pk})

        folders_resp = self.client.get(changelist_url, {param_name: "folders"})
        self.assertEqual(folders_resp.status_code, 200)
        folder_qs_ids = set(
            folders_resp.context["cl"].queryset.values_list("pk", flat=True)
        )
        self.assertEqual(folder_qs_ids, {self.root.pk, self.sub.pk})

    def test_category_admin_parent_queryset_excludes_self_descendants_and_product_holders(
        self,
    ):
        # Add form: excludes categories that already have products (self.leaf).
        add_url = reverse("admin:catalog_category_add")
        add_resp = self.client.get(add_url)
        self.assertEqual(add_resp.status_code, 200)
        add_parent_field = add_resp.context["adminform"].form.fields["parent"]
        add_parent_ids = set(add_parent_field.queryset.values_list("pk", flat=True))
        self.assertNotIn(self.leaf.pk, add_parent_ids)
        self.assertIn(self.root.pk, add_parent_ids)
        self.assertIn(self.sub.pk, add_parent_ids)
        self.assertIn(self.empty_leaf.pk, add_parent_ids)
        self.assertIn(self.other_root.pk, add_parent_ids)

        # Change form on root: excludes self, all descendants (sub, leaf, empty_leaf),
        # and any category holding products.
        change_root_url = reverse("admin:catalog_category_change", args=[self.root.pk])
        change_resp = self.client.get(change_root_url)
        self.assertEqual(change_resp.status_code, 200)
        change_parent_field = change_resp.context["adminform"].form.fields["parent"]
        change_parent_ids = set(
            change_parent_field.queryset.values_list("pk", flat=True)
        )
        self.assertNotIn(self.root.pk, change_parent_ids)
        self.assertNotIn(self.sub.pk, change_parent_ids)
        self.assertNotIn(self.leaf.pk, change_parent_ids)
        self.assertNotIn(self.empty_leaf.pk, change_parent_ids)
        self.assertIn(self.other_root.pk, change_parent_ids)

        # Change form on a leaf that already has products hides ChildCategoryInline.
        change_leaf_url = reverse("admin:catalog_category_change", args=[self.leaf.pk])
        leaf_resp = self.client.get(change_leaf_url)
        self.assertEqual(leaf_resp.status_code, 200)
        inline_models = [
            formset.opts.model
            for formset in leaf_resp.context.get("inline_admin_formsets", [])
        ]
        self.assertNotIn(Category, inline_models)

    def test_product_admin_form_limits_category_to_leaves_with_paths_and_requires_image(
        self,
    ):
        for url in (
            reverse("admin:catalog_product_add"),
            reverse("admin:catalog_product_change", args=[self.product.pk]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                form = response.context["adminform"].form
                cat_field = form.fields["category"]
                allowed_ids = set(cat_field.queryset.values_list("pk", flat=True))

                # Strictly leaf categories only.
                self.assertEqual(
                    allowed_ids,
                    {self.leaf.pk, self.empty_leaf.pk, self.other_root.pk},
                )
                self.assertNotIn(self.root.pk, allowed_ids)
                self.assertNotIn(self.sub.pk, allowed_ids)

                # Choice label displays full Windows-folder path.
                label = cat_field.label_from_instance(self.leaf)
                self.assertIn(self.leaf.full_path, label)
                self.assertContains(response, self.leaf.full_path)

                # Product.image remains required.
                self.assertTrue(form.fields["image"].required)
                self.assertFalse(Product._meta.get_field("image").blank)

    def test_product_admin_rejects_non_leaf_category_submission_cleanly(self):
        add_url = reverse("admin:catalog_product_add")
        initial_count = Product.objects.count()

        for non_leaf, slug in (
            (self.root, "post-root-product"),
            (self.sub, "post-sub-product"),
        ):
            with self.subTest(category=non_leaf.slug):
                response = self.client.post(
                    add_url,
                    {
                        "name_ar": "منتج اختباري مرفوض",
                        "name_en": "Rejected Test Product",
                        "slug": slug,
                        "category": non_leaf.pk,
                        "price_sar": "150.00",
                        "description_ar": "",
                        "description_en": "",
                        "image": _fake_image(f"{slug}.jpg"),
                        "is_active": "on",
                        "_save": "Save",
                    },
                )
                self.assertEqual(response.status_code, 200)
                form = response.context["adminform"].form
                self.assertIn("category", form.errors)
                self.assertEqual(Product.objects.count(), initial_count)

        # Valid leaf category submission succeeds cleanly.
        valid_resp = self.client.post(
            add_url,
            {
                "name_ar": "منتج اختباري مقبول",
                "name_en": "Accepted Test Product",
                "slug": "post-leaf-product",
                "category": self.empty_leaf.pk,
                "price_sar": "165.00",
                "description_ar": "وصف قصير",
                "description_en": "",
                "image": _fake_image("accepted-leaf.jpg"),
                "is_active": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(valid_resp.status_code, 302)
        self.assertTrue(Product.objects.filter(slug="post-leaf-product").exists())

        # ProductAdmin changelist renders 200 and includes full path.
        changelist = self.client.get(reverse("admin:catalog_product_changelist"))
        self.assertEqual(changelist.status_code, 200)
        self.assertContains(changelist, self.leaf.full_path)


# ---------------------------------------------------------------------------
# 3. Storefront pure folder drill-down tests
# ---------------------------------------------------------------------------


class StorefrontHierarchyDrillDownTests(_LocalMediaTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = Category.objects.create(
            name_ar="أزياء نسائية",
            name_en="Women Fashion",
            slug="sf-women-fashion",
            image=_fake_image("sf-root.jpg"),
            display_order=1,
        )
        cls.sub = Category.objects.create(
            name_ar="عبايات السهرة",
            name_en="Evening Abayas",
            slug="sf-evening-abayas",
            parent=cls.root,
            image=_fake_image("sf-sub.jpg"),
            display_order=1,
        )
        cls.leaf = Category.objects.create(
            name_ar="عبايات حرير",
            name_en="Silk Abayas",
            slug="sf-silk-abayas",
            parent=cls.sub,
            image=_fake_image("sf-leaf.jpg"),
            display_order=1,
        )
        cls.product = Product.objects.create(
            name_ar="عباية حرير ملكية",
            name_en="Royal Silk Abaya",
            slug="sf-royal-silk-abaya",
            category=cls.leaf,
            price_sar=decimal.Decimal("320.00"),
            description_ar="عباية حرير فاخرة للمناسبات",
            image=_fake_image("sf-prod.jpg"),
        )
        cls.featured = FeaturedProduct.objects.create(
            product=cls.product,
            display_order=1,
            headline_ar="تشكيلة الحرير الملكية",
        )

        # Independent second branch to confirm deactivation is scoped accurately.
        cls.other_root = Category.objects.create(
            name_ar="إكسسوارات راقية",
            name_en="Fine Accessories",
            slug="sf-fine-accessories",
            image=_fake_image("sf-other-root.jpg"),
            display_order=2,
        )
        cls.other_leaf = Category.objects.create(
            name_ar="شالات مطرزة",
            name_en="Embroidered Shawls",
            slug="sf-embroidered-shawls",
            parent=cls.other_root,
            image=_fake_image("sf-other-leaf.jpg"),
            display_order=1,
        )
        cls.other_product = Product.objects.create(
            name_ar="شال مطرز يدوي",
            name_en="Handmade Shawl",
            slug="sf-handmade-shawl",
            category=cls.other_leaf,
            price_sar=decimal.Decimal("95.00"),
            image=_fake_image("sf-other-prod.jpg"),
        )

    def test_home_and_types_list_active_root_categories_only(self):
        home_resp = self.client.get(reverse("home"))
        self.assertEqual(home_resp.status_code, 200)
        home_cat_ids = [c.id for c in home_resp.context["categories"]]
        self.assertEqual(home_cat_ids, [self.root.id, self.other_root.id])
        self.assertNotIn(self.sub.id, home_cat_ids)
        self.assertNotIn(self.leaf.id, home_cat_ids)
        self.assertNotIn(self.other_leaf.id, home_cat_ids)

        types_resp = self.client.get(reverse("product-types"))
        self.assertEqual(types_resp.status_code, 200)
        types_cat_ids = [c.id for c in types_resp.context["categories"]]
        self.assertEqual(types_cat_ids, [self.root.id, self.other_root.id])
        self.assertContains(types_resp, self.root.name_ar)
        self.assertContains(types_resp, self.other_root.name_ar)
        self.assertNotContains(types_resp, self.sub.name_ar)
        self.assertNotContains(types_resp, self.leaf.name_ar)
        self.assertNotContains(types_resp, self.other_leaf.name_ar)

    def test_root_folder_renders_subcategories_and_breadcrumbs_not_products(self):
        response = self.client.get(reverse("product-type", args=[self.root.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_folder"])
        self.assertEqual(list(response.context["subcategories"]), [self.sub])
        self.assertEqual(list(response.context["products"]), [])

        self.assertContains(response, self.sub.name_ar)
        self.assertContains(response, reverse("product-type", args=[self.sub.slug]))
        self.assertNotContains(response, self.product.name_ar)
        self.assertNotContains(response, "لا توجد منتجات متاحة في هذا التصنيف حاليا.")

        self.assertEqual(
            response.context["breadcrumbs"],
            [
                ("الرئيسية", "/"),
                ("التصنيفات", reverse("product-types")),
                (self.root.name_ar, reverse("product-type", args=[self.root.slug])),
            ],
        )
        self.assertContains(response, "الرئيسية")
        self.assertContains(response, "التصنيفات")
        self.assertContains(response, self.root.name_ar)

    def test_sub_folder_renders_leaf_subcategories_and_full_breadcrumbs(self):
        response = self.client.get(reverse("product-type", args=[self.sub.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_folder"])
        self.assertEqual(list(response.context["subcategories"]), [self.leaf])
        self.assertEqual(list(response.context["products"]), [])

        self.assertContains(response, self.leaf.name_ar)
        self.assertContains(response, reverse("product-type", args=[self.leaf.slug]))
        self.assertNotContains(response, self.product.name_ar)
        self.assertNotContains(response, "لا توجد منتجات متاحة في هذا التصنيف حاليا.")

        self.assertEqual(
            response.context["breadcrumbs"],
            [
                ("الرئيسية", "/"),
                ("التصنيفات", reverse("product-types")),
                (self.root.name_ar, reverse("product-type", args=[self.root.slug])),
                (self.sub.name_ar, reverse("product-type", args=[self.sub.slug])),
            ],
        )
        for label in ("الرئيسية", "التصنيفات", self.root.name_ar, self.sub.name_ar):
            self.assertContains(response, label)

    def test_leaf_category_renders_products_and_full_breadcrumbs(self):
        response = self.client.get(reverse("product-type", args=[self.leaf.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["is_folder"])
        self.assertEqual(list(response.context["subcategories"]), [])
        self.assertEqual(list(response.context["products"]), [self.product])

        self.assertContains(response, self.product.name_ar)
        self.assertEqual(
            response.context["breadcrumbs"],
            [
                ("الرئيسية", "/"),
                ("التصنيفات", reverse("product-types")),
                (self.root.name_ar, reverse("product-type", args=[self.root.slug])),
                (self.sub.name_ar, reverse("product-type", args=[self.sub.slug])),
                (self.leaf.name_ar, reverse("product-type", args=[self.leaf.slug])),
            ],
        )
        for label in (
            "الرئيسية",
            "التصنيفات",
            self.root.name_ar,
            self.sub.name_ar,
            self.leaf.name_ar,
        ):
            self.assertContains(response, label)

    def test_product_detail_renders_full_category_chain_breadcrumbs(self):
        response = self.client.get(reverse("product-detail", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["breadcrumbs"],
            [
                ("الرئيسية", "/"),
                ("التصنيفات", reverse("product-types")),
                (self.root.name_ar, reverse("product-type", args=[self.root.slug])),
                (self.sub.name_ar, reverse("product-type", args=[self.sub.slug])),
                (self.leaf.name_ar, reverse("product-type", args=[self.leaf.slug])),
                (
                    self.product.name_ar,
                    reverse("product-detail", args=[self.product.pk]),
                ),
            ],
        )
        for label in (
            "الرئيسية",
            "التصنيفات",
            self.root.name_ar,
            self.sub.name_ar,
            self.leaf.name_ar,
            self.product.name_ar,
        ):
            self.assertContains(response, label)
        # JSON-LD reflects the full category path.
        self.assertContains(response, self.leaf.full_path)

    def test_deactivating_root_ancestor_hides_descendants_everywhere_including_sitemap(
        self,
    ):
        self.root.is_active = False
        self.root.save()

        # Direct category & product routes return 404 for the entire hidden branch.
        for slug in (self.root.slug, self.sub.slug, self.leaf.slug):
            self.assertEqual(
                self.client.get(reverse("product-type", args=[slug])).status_code, 404
            )
        self.assertEqual(
            self.client.get(
                reverse("product-detail", args=[self.product.pk])
            ).status_code,
            404,
        )

        # Home excludes root category, hidden product, and hidden featured item.
        home_resp = self.client.get(reverse("home"))
        self.assertEqual(home_resp.status_code, 200)
        self.assertNotIn(self.root, list(home_resp.context["categories"]))
        self.assertNotIn(self.product, list(home_resp.context["products"]))
        self.assertNotIn(
            self.product, [item.product for item in home_resp.context["featured"]]
        )
        self.assertIn(self.other_product, list(home_resp.context["products"]))

        # Search excludes hidden descendant product (both filtered and unfiltered).
        search_resp = self.client.get(
            reverse("product-search"), {"q": self.product.name_ar}
        )
        self.assertEqual(search_resp.status_code, 200)
        self.assertEqual(list(search_resp.context["products"]), [])
        self.assertNotContains(
            search_resp, reverse("product-detail", args=[self.product.pk])
        )
        all_search_resp = self.client.get(reverse("product-search"))
        self.assertEqual(all_search_resp.status_code, 200)
        self.assertNotIn(self.product, list(all_search_resp.context["products"]))
        self.assertNotContains(all_search_resp, self.product.name_ar)

        # Sitemap index & section sitemaps exclude hidden branch and keep active branch.
        sitemap_index = self.client.get(reverse("django.contrib.sitemaps.views.index"))
        self.assertEqual(sitemap_index.status_code, 200)

        cat_sitemap = self.client.get(
            reverse(
                "django.contrib.sitemaps.views.sitemap",
                kwargs={"section": "categories"},
            )
        )
        self.assertEqual(cat_sitemap.status_code, 200)
        for hidden_slug in (self.root.slug, self.sub.slug, self.leaf.slug):
            self.assertNotContains(cat_sitemap, hidden_slug)
        self.assertContains(cat_sitemap, self.other_root.slug)
        self.assertContains(cat_sitemap, self.other_leaf.slug)

        prod_sitemap = self.client.get(
            reverse(
                "django.contrib.sitemaps.views.sitemap",
                kwargs={"section": "products"},
            )
        )
        self.assertEqual(prod_sitemap.status_code, 200)
        self.assertNotContains(
            prod_sitemap, reverse("product-detail", args=[self.product.pk])
        )
        self.assertContains(
            prod_sitemap, reverse("product-detail", args=[self.other_product.pk])
        )

    def test_deactivating_intermediate_ancestor_hides_leaf_and_products(self):
        self.sub.is_active = False
        self.sub.save()

        # Root stays accessible (200) as a folder, but has no active subcategories.
        root_resp = self.client.get(reverse("product-type", args=[self.root.slug]))
        self.assertEqual(root_resp.status_code, 200)
        self.assertEqual(list(root_resp.context["subcategories"]), [])

        # Inactive intermediate and its leaf descendant return 404.
        self.assertEqual(
            self.client.get(reverse("product-type", args=[self.sub.slug])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("product-type", args=[self.leaf.slug])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("product-detail", args=[self.product.pk])
            ).status_code,
            404,
        )

        # Excluded from home, search, and sitemaps.
        home_resp = self.client.get(reverse("home"))
        self.assertNotIn(self.product, list(home_resp.context["products"]))
        self.assertNotIn(
            self.product, [item.product for item in home_resp.context["featured"]]
        )

        search_resp = self.client.get(reverse("product-search"))
        self.assertNotContains(search_resp, self.product.name_ar)

        cat_sitemap = self.client.get(
            reverse(
                "django.contrib.sitemaps.views.sitemap",
                kwargs={"section": "categories"},
            )
        )
        self.assertContains(cat_sitemap, self.root.slug)
        self.assertNotContains(cat_sitemap, self.sub.slug)
        self.assertNotContains(cat_sitemap, self.leaf.slug)

        prod_sitemap = self.client.get(
            reverse(
                "django.contrib.sitemaps.views.sitemap",
                kwargs={"section": "products"},
            )
        )
        self.assertNotContains(
            prod_sitemap, reverse("product-detail", args=[self.product.pk])
        )


# ---------------------------------------------------------------------------
# 4. Placeholder image tests
# ---------------------------------------------------------------------------


class PlaceholderImageTests(_LocalMediaTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = Category.objects.create(
            name_ar="مجموعة الصيف",
            name_en="Summer Collection",
            slug="ph-summer",
            image=_fake_image("ph-root.jpg"),
            display_order=1,
        )
        cls.leaf = Category.objects.create(
            name_ar="فساتين صيفية",
            name_en="Summer Dresses",
            slug="ph-summer-dresses",
            parent=cls.root,
            image=_fake_image("ph-leaf.jpg"),
            display_order=1,
        )
        cls.product = Product.objects.create(
            name_ar="فستان صيفي ناعم",
            name_en="Soft Summer Dress",
            slug="ph-soft-dress",
            category=cls.leaf,
            price_sar=decimal.Decimal("145.00"),
            image=_fake_image("ph-prod.jpg"),
        )
        cls.featured = FeaturedProduct.objects.create(
            product=cls.product,
            display_order=1,
            headline_ar="أجمل فساتين الصيف",
        )

    def test_placeholder_svg_exists_on_disk_and_contains_svg_markup(self):
        svg_path = (
            Path(settings.BASE_DIR)
            / "static"
            / "images"
            / "product-placeholder.svg"
        )
        self.assertTrue(
            svg_path.is_file(),
            f"Expected placeholder SVG at {svg_path}.",
        )
        content = svg_path.read_text(encoding="utf-8")
        self.assertIn("<svg", content)
        self.assertIn("</svg>", content)

    def test_storefront_pages_render_placeholder_onerror_fallback(self):
        # Home page renders featured slider, product cards, and root categories strip.
        home_resp = self.client.get(reverse("home"))
        self.assertEqual(home_resp.status_code, 200)
        home_html = home_resp.content.decode("utf-8")
        self.assertIn("data-featured-slider", home_html)
        home_imgs = _collect_images(home_html)
        fallback_imgs = [
            img
            for img in home_imgs
            if "product-placeholder.svg" in (img.get("onerror") or "")
        ]
        # Expect fallbacks for featured slider image, product card image, and category image.
        self.assertGreaterEqual(
            len(fallback_imgs),
            3,
            f"Expected onerror placeholder fallbacks across featured slider, product card, and categories on /, got {fallback_imgs}.",
        )

        # Product detail page
        detail_resp = self.client.get(reverse("product-detail", args=[self.product.pk]))
        self.assertEqual(detail_resp.status_code, 200)
        detail_imgs = _collect_images(detail_resp.content.decode("utf-8"))
        self.assertTrue(
            any(
                "product-placeholder.svg" in (img.get("onerror") or "")
                for img in detail_imgs
            ),
            "Expected product detail image to have product-placeholder.svg onerror fallback.",
        )

        # Root categories index (/products/types/)
        types_resp = self.client.get(reverse("product-types"))
        self.assertEqual(types_resp.status_code, 200)
        types_imgs = _collect_images(types_resp.content.decode("utf-8"))
        self.assertTrue(
            any(
                "product-placeholder.svg" in (img.get("onerror") or "")
                for img in types_imgs
            ),
            "Expected /types/ category cards to have product-placeholder.svg onerror fallback.",
        )

        # Parent folder subcategory page (/products/types/<root>/)
        folder_resp = self.client.get(reverse("product-type", args=[self.root.slug]))
        self.assertEqual(folder_resp.status_code, 200)
        folder_imgs = _collect_images(folder_resp.content.decode("utf-8"))
        self.assertTrue(
            any(
                "product-placeholder.svg" in (img.get("onerror") or "")
                for img in folder_imgs
            ),
            "Expected /types/<root>/ subcategory cards to have product-placeholder.svg onerror fallback.",
        )

        # Leaf category product listing (/products/types/<leaf>/)
        leaf_resp = self.client.get(reverse("product-type", args=[self.leaf.slug]))
        self.assertEqual(leaf_resp.status_code, 200)
        leaf_imgs = _collect_images(leaf_resp.content.decode("utf-8"))
        self.assertTrue(
            any(
                "product-placeholder.svg" in (img.get("onerror") or "")
                for img in leaf_imgs
            ),
            "Expected /types/<leaf>/ product cards to have product-placeholder.svg onerror fallback.",
        )

    def test_empty_product_and_category_images_render_placeholder_without_errors(self):
        # Simulate empty DB image fields without bypassing production form requirements.
        Product.objects.filter(pk=self.product.pk).update(image="")
        Category.objects.filter(pk__in=[self.root.pk, self.leaf.pk]).update(image="")

        for url in (
            reverse("home"),
            reverse("product-detail", args=[self.product.pk]),
            reverse("product-types"),
            reverse("product-type", args=[self.root.slug]),
            reverse("product-type", args=[self.leaf.slug]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                imgs = _collect_images(response.content.decode("utf-8"))
                self.assertTrue(
                    any(
                        "product-placeholder.svg" in (img.get("src") or "")
                        for img in imgs
                    ),
                    f"Expected placeholder <img src> on {url} when image field is empty.",
                )
