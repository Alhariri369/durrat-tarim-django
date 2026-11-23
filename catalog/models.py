import re
import uuid
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _unique_filename(instance, filename):
    ext = Path(filename).suffix.lower()
    return f"{instance._meta.model_name}s/{uuid.uuid4().hex}{ext}"


def _validate_hex_color(value):
    if not HEX_COLOR_RE.match(value):
        raise ValidationError("أدخل رمز لون سداسي صحيح مثل #30669c")


class Category(models.Model):
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="التصنيف الأب",
    )
    name_ar = models.CharField("الاسم (عربي)", max_length=200, db_index=True)
    name_en = models.CharField(
        "الاسم (إنجليزي)", max_length=200, blank=True, default=""
    )
    slug = models.SlugField("المعرف", max_length=256, unique=True)
    image = models.ImageField("الصورة الرئيسية", upload_to=_unique_filename)
    is_active = models.BooleanField("نشط", default=True)
    display_order = models.PositiveIntegerField("ترتيب العرض", default=0)
    created_at = models.DateTimeField("تاريخ الإنشاء", default=timezone.now)
    updated_at = models.DateTimeField("تاريخ التعديل", default=timezone.now)

    class Meta:
        db_table = "categories"
        ordering = ["display_order", "name_ar"]
        verbose_name = "تصنيف"
        verbose_name_plural = "التصنيفات"

    @property
    def is_root(self):
        return self.parent_id is None

    @property
    def is_leaf(self):
        annotated = getattr(self, "_children_count", None)
        if annotated is not None:
            return annotated == 0
        if self.pk is None:
            return True
        return not self.children.exists()

    def get_ancestors(self):
        ancestors = []
        visited = set()
        if self.pk is not None:
            visited.add(self.pk)
        current = self.parent
        while current is not None:
            if current.pk is not None:
                if current.pk in visited:
                    break
                visited.add(current.pk)
            ancestors.append(current)
            current = current.parent
        ancestors.reverse()
        return ancestors

    def get_path_categories(self):
        return self.get_ancestors() + [self]

    @property
    def full_path(self):
        return " / ".join(c.name_ar for c in self.get_path_categories())

    @property
    def depth(self):
        return len(self.get_ancestors())

    @classmethod
    def active_category_ids(cls):
        rows = cls.objects.values_list("id", "parent_id", "is_active")
        nodes = {
            cat_id: (parent_id, is_active)
            for cat_id, parent_id, is_active in rows
        }
        memo = {}

        def is_chain_active(cat_id):
            if cat_id in memo:
                return memo[cat_id]
            visited = set()
            path = []
            curr = cat_id
            result = True
            while curr is not None:
                if curr in memo:
                    result = memo[curr]
                    break
                if curr in visited:
                    result = False
                    break
                node = nodes.get(curr)
                if node is None:
                    result = False
                    break
                visited.add(curr)
                path.append(curr)
                parent_id, active = node
                if not active:
                    result = False
                    break
                curr = parent_id
            for node_id in path:
                memo[node_id] = result
            return result

        return {cat_id for cat_id in nodes if is_chain_active(cat_id)}

    @classmethod
    def leaf_queryset(cls):
        return cls.objects.filter(children__isnull=True)

    @classmethod
    def tree_ordered_categories(cls, queryset=None):
        if queryset is None:
            cats = list(cls.objects.select_related("parent"))
        else:
            cats = list(queryset)
        if not cats:
            return []

        by_id = {c.pk: c for c in cats}
        has_missing_parent = any(
            c.parent_id is not None and c.parent_id not in by_id for c in cats
        )

        if not has_missing_parent:
            children_map = {}
            for c in cats:
                children_map.setdefault(c.parent_id, []).append(c)
            for siblings in children_map.values():
                siblings.sort(key=lambda c: (c.display_order, c.name_ar, c.pk or 0))

            ordered = []
            visited = set()

            def dfs(parent_id):
                for child in children_map.get(parent_id, ()):
                    if child.pk in visited:
                        continue
                    visited.add(child.pk)
                    ordered.append(child)
                    dfs(child.pk)

            dfs(None)
            if len(ordered) < len(cats):
                remaining = [c for c in cats if c.pk not in visited]
                remaining.sort(key=lambda c: (c.display_order, c.name_ar, c.pk or 0))
                ordered.extend(remaining)
            return ordered

        rows = cls.objects.values_list("id", "parent_id", "display_order", "name_ar")
        all_children = {}
        for cat_id, parent_id, display_order, name_ar in rows:
            all_children.setdefault(parent_id, []).append(
                (display_order, name_ar, cat_id)
            )
        for siblings in all_children.values():
            siblings.sort()

        ordered = []
        visited = set()

        def dfs_ids(parent_id):
            for _, _, cat_id in all_children.get(parent_id, ()):
                if cat_id in visited:
                    continue
                visited.add(cat_id)
                if cat_id in by_id:
                    ordered.append(by_id[cat_id])
                dfs_ids(cat_id)

        dfs_ids(None)
        if len(ordered) < len(cats):
            included = {c.pk for c in ordered}
            remaining = [c for c in cats if c.pk not in included]
            remaining.sort(key=lambda c: (c.display_order, c.name_ar, c.pk or 0))
            ordered.extend(remaining)
        return ordered

    def get_absolute_url(self):
        return reverse("product-type", args=[self.slug])

    def clean(self):
        super().clean()
        if self._state.fields_cache.get("parent") is self:
            raise ValidationError({"parent": "لا يمكن أن يكون التصنيف أباً لنفسه."})
        if self.parent_id is not None:
            if self.pk is not None and self.parent_id == self.pk:
                raise ValidationError({"parent": "لا يمكن أن يكون التصنيف أباً لنفسه."})
            if self.pk is not None:
                visited = {self.pk}
                current_id = self.parent_id
                while current_id is not None:
                    if current_id == self.pk:
                        raise ValidationError(
                            {
                                "parent": "لا يمكن جعل التصنيف أباً لأحد فروعه (حلقة مفرغة)."
                            }
                        )
                    if current_id in visited:
                        break
                    visited.add(current_id)
                    current_id = (
                        Category.objects.filter(pk=current_id)
                        .values_list("parent_id", flat=True)
                        .first()
                    )
            if Product.objects.filter(category_id=self.parent_id).exists():
                raise ValidationError(
                    {
                        "parent": "لا يمكن إضافة تصنيف فرعي داخل تصنيف يحتوي على منتجات. يرجى نقل المنتجات أو حذفها أولاً."
                    }
                )

    def save(self, *args, **kwargs):
        self.clean()
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name_ar


class Product(models.Model):
    name_ar = models.CharField("الاسم (عربي)", max_length=200, db_index=True)
    name_en = models.CharField(
        "الاسم (إنجليزي)", max_length=200, blank=True, default=""
    )
    description_ar = models.TextField("الوصف (عربي)", blank=True, default="")
    description_en = models.TextField("الوصف (إنجليزي)", blank=True, default="")
    slug = models.SlugField("المعرف", max_length=256, unique=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="التصنيف",
    )
    price_sar = models.DecimalField(
        "السعر (ر.س)",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    image = models.ImageField("الصورة الرئيسية", upload_to=_unique_filename)
    is_active = models.BooleanField("نشط", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", default=timezone.now)
    updated_at = models.DateTimeField("تاريخ التعديل", default=timezone.now)

    class Meta:
        db_table = "products"
        ordering = ["-created_at"]
        verbose_name = "منتج"
        verbose_name_plural = "المنتجات"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price_sar__gte=0),
                name="price_sar_non_negative",
            ),
        ]

    def get_absolute_url(self):
        # The storefront detail URL is keyed by pk, not slug.
        return reverse("product-detail", args=[self.pk])

    def clean(self):
        super().clean()
        if (
            self.category_id is not None
            and Category.objects.filter(parent_id=self.category_id).exists()
        ):
            raise ValidationError(
                {
                    "category": "لا يمكن إضافة المنتج إلى تصنيف أب. يرجى اختيار تصنيف نهائي لا يحتوي على تصنيفات فرعية."
                }
            )

    def save(self, *args, **kwargs):
        self.clean()
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name_ar


class Favorite(models.Model):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="favorites",
        verbose_name="المستخدم",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="favorites",
        verbose_name="المنتج",
    )
    created_at = models.DateTimeField("تاريخ الإضافة", auto_now_add=True)

    class Meta:
        db_table = "favorites"
        ordering = ["-created_at", "-id"]
        verbose_name = "مفضلة"
        verbose_name_plural = "المفضلات"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"], name="unique_user_product_favorite"
            )
        ]

    def __str__(self):
        return f"{self.user}: {self.product.name_ar}"


class FeaturedProduct(models.Model):
    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        verbose_name="المنتج",
    )
    display_order = models.IntegerField("ترتيب العرض", default=0)
    is_active = models.BooleanField("نشط", default=True)
    headline_ar = models.CharField(
        "العنوان الترويجي (عربي)", max_length=300, blank=True, default=""
    )
    headline_en = models.CharField(
        "العنوان الترويجي (إنجليزي)", max_length=300, blank=True, default=""
    )
    subtitle_ar = models.CharField(
        "العنوان الفرعي (عربي)", max_length=500, blank=True, default=""
    )
    subtitle_en = models.CharField(
        "العنوان الفرعي (إنجليزي)", max_length=500, blank=True, default=""
    )
    created_at = models.DateTimeField("تاريخ الإنشاء", default=timezone.now)
    updated_at = models.DateTimeField("تاريخ التعديل", default=timezone.now)

    class Meta:
        db_table = "featured_products"
        ordering = ["display_order", "id"]
        verbose_name = "منتج مميز"
        verbose_name_plural = "المنتجات المميزة"

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"مميز: {self.product.name_ar}"


class StoreSettings(models.Model):
    sar_to_yer_rate = models.DecimalField(
        "سعر صرف الريال مقابل الريال اليمني",
        max_digits=8,
        decimal_places=2,
        default=410,
        validators=[MinValueValidator(0.01)],
    )
    local_phone = models.CharField(
        "رقم الجوال المحلي", max_length=30, default="783278181"
    )
    whatsapp_number = models.CharField(
        "رقم واتساب دولي", max_length=30, default="967783278181"
    )
    address_ar = models.TextField("العنوان (عربي)", blank=True, default="")
    address_en = models.TextField("العنوان (إنجليزي)", blank=True, default="")

    light_color_primary = models.CharField(
        "اللون الأساسي (فاتح)",
        max_length=7,
        default="#6b4c8c",
        validators=[_validate_hex_color],
        help_text="Token: --color-primary",
    )
    light_color_secondary = models.CharField(
        "اللون الثانوي (فاتح)",
        max_length=7,
        default="#1f1629",
        validators=[_validate_hex_color],
        help_text="Token: --color-secondary",
    )
    light_color_accent = models.CharField(
        "لون التمييز (فاتح)",
        max_length=7,
        default="#a974c4",
        validators=[_validate_hex_color],
        help_text="Token: --color-accent",
    )
    light_color_background = models.CharField(
        "لون الخلفية (فاتح)",
        max_length=7,
        default="#f7f3fa",
        validators=[_validate_hex_color],
        help_text="Token: --color-background",
    )
    light_color_surface = models.CharField(
        "لون السطح (فاتح)",
        max_length=7,
        default="#ffffff",
        validators=[_validate_hex_color],
        help_text="Token: --color-surface",
    )
    dark_color_primary = models.CharField(
        "اللون الأساسي (داكن)",
        max_length=7,
        default="#c9a7eb",
        validators=[_validate_hex_color],
        help_text="Token: --color-primary (dark)",
    )
    dark_color_secondary = models.CharField(
        "اللون الثانوي (داكن)",
        max_length=7,
        default="#efe8f7",
        validators=[_validate_hex_color],
        help_text="Token: --color-secondary (dark)",
    )
    dark_color_accent = models.CharField(
        "لون التمييز (داكن)",
        max_length=7,
        default="#d8a7f0",
        validators=[_validate_hex_color],
        help_text="Token: --color-accent (dark)",
    )
    dark_color_background = models.CharField(
        "لون الخلفية (داكن)",
        max_length=7,
        default="#140d1c",
        validators=[_validate_hex_color],
        help_text="Token: --color-background (dark)",
    )
    dark_color_surface = models.CharField(
        "لون السطح (داكن)",
        max_length=7,
        default="#1e1429",
        validators=[_validate_hex_color],
        help_text="Token: --color-surface (dark)",
    )

    contact_cooldown_seconds = models.PositiveIntegerField(
        "فترة التبريد بين الرسائل (ثانية)",
        default=600,
        help_text="الحد الأدنى للفاصل الزمني بين رسائل التواصل (بالثواني)",
    )
    contact_daily_limit = models.PositiveIntegerField(
        "الحد اليومي للرسائل",
        default=5,
        help_text="الحد اليومي الأقصى لرسائل التواصل لكل مستخدم",
    )
    analytics_retention_days = models.PositiveIntegerField(
        "مدة الاحتفاظ ببيانات التحليلات (يوم)",
        default=90,
        help_text="عدد الأيام للاحتفاظ ببيانات التحليلات قبل حذفها",
    )
    updated_at = models.DateTimeField("تاريخ التعديل", auto_now=True)

    class Meta:
        db_table = "store_settings"
        verbose_name = "إعدادات المتجر"
        verbose_name_plural = "إعدادات المتجر"

    def save(self, *args, **kwargs):
        if not self.pk and StoreSettings.objects.exists():
            raise ValidationError(
                "يوجد إعداد واحد فقط للمتجر. لا يمكن إنشاء إعداد جديد."
            )
        super().save(*args, **kwargs)

    @classmethod
    def get_current(cls):
        from django.core.cache import cache

        cache_key = "store_settings_current"
        settings = cache.get(cache_key)
        if settings is None:
            settings = cls.objects.first()
            if settings is None:
                settings = cls.objects.create()
            cache.set(cache_key, settings, timeout=3600)
        return settings

    @classmethod
    def invalidate_cache(cls):
        from django.core.cache import cache

        cache.delete("store_settings_current")

    def __str__(self):
        return "إعدادات المتجر"
