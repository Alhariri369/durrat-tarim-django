from django import forms
from django.contrib import admin
from django.utils.html import format_html

from .currency import invalidate_rate_cache
from .image_storage import handle_image_deletion, handle_image_replacement
from .models import (
    HEX_COLOR_RE,
    Category,
    Favorite,
    FeaturedProduct,
    Product,
    StoreSettings,
)


def _image_preview(obj, field_name="image", width=80):
    """Return an <img> tag for admin list-display preview, or '-'."""
    image_field = getattr(obj, field_name, None)
    if not image_field or not image_field.name:
        return "-"
    try:
        url = image_field.url
    except Exception:
        return "—"
    return format_html(
        '<img src="{}" width="{}" height="{}" style="object-fit:cover;border-radius:4px" />',
        url,
        width,
        width,
    )


class _ImagePreviewAdminMixin:
    """Mixin that shows image preview in admin forms via a read-only field."""

    readonly_fields = ("image_preview",)

    @admin.display(description="معاينة الصورة")
    def image_preview(self, obj):
        return _image_preview(obj)


def _color_swatch(value):
    """Render a hex color value as a small swatch with the value next to it."""
    if not value:
        return "-"
    return format_html(
        '<span style="display:inline-flex;align-items:center;gap:6px;'
        'font-family:monospace;font-size:12px;">'
        '<span style="width:18px;height:18px;border-radius:4px;'
        'border:1px solid rgba(0,0,0,0.15);background:{};"></span>'
        "<span>{}</span></span>",
        value,
        value,
    )


class _ColorPreviewAdminMixin:
    """Mixin that renders read-only color swatches next to color fields."""

    readonly_fields = ("light_color_preview", "dark_color_preview")

    @admin.display(description="معاينة الألوان (فاتح)")
    def light_color_preview(self, obj):
        if not obj or not obj.pk:
            return "-"
        return format_html(
            '<div style="display:flex;flex-wrap:wrap;gap:8px;">'
            "{}{}{}{}{}</div>",
            _color_swatch(getattr(obj, "light_color_primary", "")),
            _color_swatch(getattr(obj, "light_color_secondary", "")),
            _color_swatch(getattr(obj, "light_color_accent", "")),
            _color_swatch(getattr(obj, "light_color_background", "")),
            _color_swatch(getattr(obj, "light_color_surface", "")),
        )

    @admin.display(description="معاينة الألوان (داكن)")
    def dark_color_preview(self, obj):
        if not obj or not obj.pk:
            return "-"
        return format_html(
            '<div style="display:flex;flex-wrap:wrap;gap:8px;">'
            "{}{}{}{}{}</div>",
            _color_swatch(getattr(obj, "dark_color_primary", "")),
            _color_swatch(getattr(obj, "dark_color_secondary", "")),
            _color_swatch(getattr(obj, "dark_color_accent", "")),
            _color_swatch(getattr(obj, "dark_color_background", "")),
            _color_swatch(getattr(obj, "dark_color_surface", "")),
        )


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------


@admin.register(Category)
class CategoryAdmin(_ImagePreviewAdminMixin, admin.ModelAdmin):
    list_display = (
        "image_preview",
        "name_ar",
        "name_en",
        "slug",
        "is_active",
        "display_order",
        "created_at",
    )
    list_editable = ("is_active", "display_order")
    list_filter = ("is_active",)
    search_fields = ("name_ar", "name_en", "slug")
    prepopulated_fields = {"slug": ("name_en",)}
    readonly_fields = _ImagePreviewAdminMixin.readonly_fields + (
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            "المعلومات الأساسية",
            {"fields": (("name_ar", "name_en"), "slug", "image", "image_preview")},
        ),
        (
            "الإعدادات",
            {"fields": ("is_active", "display_order")},
        ),
        (
            "التواريخ",
            {"fields": ("created_at", "updated_at")},
        ),
    )

    def save_model(self, request, obj, form, change):
        if change and "image" in form.changed_data:
            handle_image_replacement(obj, form.cleaned_data.get("image"))
        else:
            super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        handle_image_deletion(obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            handle_image_deletion(obj)
        super().delete_queryset(request, queryset)


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------


@admin.register(Product)
class ProductAdmin(_ImagePreviewAdminMixin, admin.ModelAdmin):
    list_display = (
        "image_preview",
        "name_ar",
        "name_en",
        "category",
        "price_sar",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "category")
    list_select_related = ("category",)
    search_fields = ("name_ar", "name_en", "description_ar", "description_en")
    prepopulated_fields = {"slug": ("name_en",)}
    autocomplete_fields = ("category",)
    readonly_fields = _ImagePreviewAdminMixin.readonly_fields + (
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            "المعلومات الأساسية",
            {
                "fields": (
                    ("name_ar", "name_en"),
                    "slug",
                    "category",
                    "price_sar",
                    "image",
                    "image_preview",
                )
            },
        ),
        (
            "الوصف",
            {"fields": ("description_ar", "description_en")},
        ),
        (
            "الإعدادات",
            {"fields": ("is_active",)},
        ),
        (
            "التواريخ",
            {"fields": ("created_at", "updated_at")},
        ),
    )

    def save_model(self, request, obj, form, change):
        if change and "image" in form.changed_data:
            handle_image_replacement(obj, form.cleaned_data.get("image"))
        else:
            super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        handle_image_deletion(obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            handle_image_deletion(obj)
        super().delete_queryset(request, queryset)


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at")
    list_select_related = ("user", "product")
    search_fields = ("user__email", "product__name_ar")
    autocomplete_fields = ("user", "product")
    readonly_fields = ("created_at",)


# ---------------------------------------------------------------------------
# FeaturedProduct
# ---------------------------------------------------------------------------


@admin.register(FeaturedProduct)
class FeaturedProductAdmin(admin.ModelAdmin):
    list_display = (
        "_product_image",
        "_product_name",
        "display_order",
        "is_active",
        "updated_at",
    )
    list_editable = ("display_order", "is_active")
    list_filter = ("is_active",)
    list_select_related = ("product",)
    autocomplete_fields = ("product",)
    search_fields = (
        "product__name_ar",
        "product__name_en",
        "headline_ar",
        "headline_en",
    )
    readonly_fields = ("_product_preview", "created_at", "updated_at")
    fieldsets = (
        (
            "المنتج",
            {"fields": ("product", "_product_preview")},
        ),
        (
            "النص الترويجي (عربي)",
            {"fields": ("headline_ar", "subtitle_ar")},
        ),
        (
            "النص الترويجي (إنجليزي)",
            {"fields": ("headline_en", "subtitle_en")},
        ),
        (
            "الإعدادات",
            {"fields": ("display_order", "is_active")},
        ),
        (
            "التواريخ",
            {"fields": ("created_at", "updated_at")},
        ),
    )

    @admin.display(description="المنتج")
    def _product_name(self, obj):
        return obj.product.name_ar

    @admin.display(description="الصورة")
    def _product_image(self, obj):
        return _image_preview(obj.product, width=50)

    @admin.display(description="معاينة المنتج")
    def _product_preview(self, obj):
        if not obj or not obj.pk:
            return "-"
        return _image_preview(obj.product, width=200)


# ---------------------------------------------------------------------------
# StoreSettings (singleton — only one row allowed)
# ---------------------------------------------------------------------------

_STORE_SETTINGS_COLOR_FIELDS = frozenset(
    {
        "light_color_primary",
        "light_color_secondary",
        "light_color_accent",
        "light_color_background",
        "light_color_surface",
        "dark_color_primary",
        "dark_color_secondary",
        "dark_color_accent",
        "dark_color_background",
        "dark_color_surface",
    }
)


class HexColorPickerWidget(forms.TextInput):
    """Hex color text input paired with a two-way synced native color picker."""

    def __init__(self, attrs=None):
        default_attrs = {
            "class": "vTextField",
            "dir": "ltr",
            "style": "width: 9ch; font-family: monospace;",
            "autocomplete": "off",
            "spellcheck": "false",
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)

    def render(self, name, value, attrs=None, renderer=None):
        raw_value = "" if value is None else str(value).strip()
        picker_value = (
            raw_value.lower() if HEX_COLOR_RE.match(raw_value) else "#000000"
        )

        text_attrs = dict(attrs) if attrs else {}
        text_attrs["oninput"] = (
            "var p=this.parentElement&&this.parentElement.querySelector('input[type=color]');"
            "var v=this.value.trim();"
            "if(p&&/^#[0-9a-fA-F]{6}$/.test(v)){p.value=v.toLowerCase();}"
        )

        text_input_html = super().render(
            name, value, attrs=text_attrs, renderer=renderer
        )
        picker_oninput = (
            "var t=this.parentElement&&this.parentElement.querySelector('input[type=text]');"
            "if(t){t.value=this.value;}"
        )

        return format_html(
            '<span style="display:inline-flex;align-items:center;gap:8px;vertical-align:middle;">'
            "{}"
            '<input type="color" value="{}" aria-label="{}" '
            'style="width:38px;height:32px;padding:2px;border:1px solid var(--border-color, #ccc);'
            'border-radius:4px;background:transparent;cursor:pointer;" '
            'oninput="{}" />'
            "</span>",
            text_input_html,
            picker_value,
            name,
            picker_oninput,
        )


@admin.register(StoreSettings)
class StoreSettingsAdmin(_ColorPreviewAdminMixin, admin.ModelAdmin):
    fieldsets = (
        (
            "العملة",
            {"fields": ("sar_to_yer_rate",)},
        ),
        (
            "معلومات التواصل",
            {"fields": ("local_phone", "whatsapp_number")},
        ),
        (
            "العنوان",
            {"fields": ("address_ar", "address_en")},
        ),
        (
            "ألوان الوضع الفاتح",
            {
                "fields": (
                    "light_color_primary",
                    "light_color_secondary",
                    "light_color_accent",
                    "light_color_background",
                    "light_color_surface",
                    "light_color_preview",
                )
            },
        ),
        (
            "ألوان الوضع الداكن",
            {
                "fields": (
                    "dark_color_primary",
                    "dark_color_secondary",
                    "dark_color_accent",
                    "dark_color_background",
                    "dark_color_surface",
                    "dark_color_preview",
                )
            },
        ),
        (
            "حدود التواصل",
            {
                "fields": (
                    "contact_cooldown_seconds",
                    "contact_daily_limit",
                )
            },
        ),
        (
            "التحليلات",
            {"fields": ("analytics_retention_days",)},
        ),
    )
    readonly_fields = _ColorPreviewAdminMixin.readonly_fields + ("updated_at",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in _STORE_SETTINGS_COLOR_FIELDS:
            kwargs["widget"] = HexColorPickerWidget()
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def has_add_permission(self, request):
        """Prevent creating a second settings row through the admin."""
        if StoreSettings.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        """Prevent deleting the singleton settings row."""
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        StoreSettings.invalidate_cache()
        invalidate_rate_cache()
