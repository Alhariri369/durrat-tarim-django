import re
import uuid
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _unique_filename(instance, filename):
    ext = Path(filename).suffix.lower()
    return f"{instance._meta.model_name}s/{uuid.uuid4().hex}{ext}"


def _validate_hex_color(value):
    if not HEX_COLOR_RE.match(value):
        raise ValidationError("أدخل رمز لون سداسي صحيح مثل #30669c")


class Category(models.Model):
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

    def save(self, *args, **kwargs):
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

    def save(self, *args, **kwargs):
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
        default="#30669c",
        validators=[_validate_hex_color],
    )
    light_color_secondary = models.CharField(
        "اللون الثانوي (فاتح)",
        max_length=7,
        default="#08121b",
        validators=[_validate_hex_color],
    )
    light_color_accent = models.CharField(
        "لون التمييز (فاتح)",
        max_length=7,
        default="#e0801f",
        validators=[_validate_hex_color],
    )
    light_color_background = models.CharField(
        "لون الخلفية (فاتح)",
        max_length=7,
        default="#f6f1ee",
        validators=[_validate_hex_color],
    )
    light_color_surface = models.CharField(
        "لون السطح (فاتح)",
        max_length=7,
        default="#ffffff",
        validators=[_validate_hex_color],
    )
    dark_color_primary = models.CharField(
        "اللون الأساسي (داكن)",
        max_length=7,
        default="#39f2f9",
        validators=[_validate_hex_color],
    )
    dark_color_secondary = models.CharField(
        "اللون الثانوي (داكن)",
        max_length=7,
        default="#e0ebe7",
        validators=[_validate_hex_color],
    )
    dark_color_accent = models.CharField(
        "لون التمييز (داكن)",
        max_length=7,
        default="#e7994b",
        validators=[_validate_hex_color],
    )
    dark_color_background = models.CharField(
        "لون الخلفية (داكن)",
        max_length=7,
        default="#08121b",
        validators=[_validate_hex_color],
    )
    dark_color_surface = models.CharField(
        "لون السطح (داكن)",
        max_length=7,
        default="#0c1927",
        validators=[_validate_hex_color],
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
