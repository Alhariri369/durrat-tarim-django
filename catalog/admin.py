import logging
from typing import ClassVar

import requests
from django import forms
from django.contrib import admin, messages
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Case, Count, IntegerField, Value, When
from django.http import HttpResponseRedirect
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import format_html

from .currency import invalidate_rate_cache
from .image_storage import (
    _cleanup_old_image,
    _require_durable_storage,
    _validate_image,
)
from .models import (
    HEX_COLOR_RE,
    Category,
    Favorite,
    FeaturedProduct,
    Product,
    StoreSettings,
)

logger = logging.getLogger(__name__)

IMAGE_UPLOAD_ERROR_MESSAGE = (
    "تعذر رفع الصورة إلى خدمة التخزين حالياً. لم يتم حفظ التغييرات، "
    "يرجى المحاولة مرة أخرى أو التحقق من إعدادات التخزين."
)


class ImageUploadError(Exception):
    """Raised when persisting an uploaded image to storage fails."""


class _ValidatedImageAdminFormMixin:
    """Validate newly uploaded images on both add and change forms."""

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if isinstance(image, UploadedFile):
            _validate_image(image)
        return image


class CategoryAdminForm(_ValidatedImageAdminFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = "__all__"


class ProductAdminForm(_ValidatedImageAdminFormMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = "__all__"


class _SafeImageUploadAdminMixin:
    """Validate images on add/change and handle storage upload failures cleanly."""

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        try:
            return super().changeform_view(
                request, object_id, form_url, extra_context
            )
        except (ImageUploadError, requests.RequestException, OSError) as exc:
            if not isinstance(exc, ImageUploadError):
                logger.exception(
                    "Storage failure during %s changeform_view",
                    self.model.__name__,
                )
            self.message_user(
                request,
                str(exc) if isinstance(exc, ImageUploadError) else IMAGE_UPLOAD_ERROR_MESSAGE,
                level=messages.ERROR,
            )
            return HttpResponseRedirect(request.get_full_path())

    def save_model(self, request, obj, form, change):
        new_image = form.cleaned_data.get("image")
        has_new_upload = isinstance(new_image, UploadedFile)
        old_image_name = None

        if change and obj.pk and "image" in form.changed_data:
            old_image_name = (
                type(obj)
                .objects.filter(pk=obj.pk)
                .values_list("image", flat=True)
                .first()
            )

        if has_new_upload:
            try:
                _require_durable_storage()
            except RuntimeError as exc:
                logger.exception(
                    "Durable storage check failed for %s", type(obj).__name__
                )
                raise ImageUploadError(IMAGE_UPLOAD_ERROR_MESSAGE) from exc
            _validate_image(new_image)

        try:
            super().save_model(request, obj, form, change)
        except (requests.RequestException, OSError, RuntimeError) as exc:
            logger.exception(
                "Image upload failed while saving %s (change=%s)",
                type(obj).__name__,
                change,
            )
            raise ImageUploadError(IMAGE_UPLOAD_ERROR_MESSAGE) from exc

        if change and old_image_name and old_image_name != obj.image.name:
            _cleanup_old_image(old_image_name, obj.image.name, type(obj))

    def delete_model(self, request, obj):
        image_name = obj.image.name if obj.image else ""
        model_class = type(obj)
        super().delete_model(request, obj)
        if image_name:
            _cleanup_old_image(image_name, None, model_class)

    def delete_queryset(self, request, queryset):
        image_names = [
            obj.image.name
            for obj in queryset
            if getattr(obj, "image", None) and obj.image.name
        ]
        model_class = queryset.model
        super().delete_queryset(request, queryset)
        for image_name in set(image_names):
            _cleanup_old_image(image_name, None, model_class)


def _image_preview(obj, field_name="image", width=80):
    """Return an <img> tag for admin list-display preview, or '-'."""
    image_field = getattr(obj, field_name, None)
    if not image_field or not image_field.name:
        return "-"
    try:
        url = image_field.url
    except (ValueError, OSError, AttributeError):
        return "—"
    placeholder_url = static("images/product-placeholder.svg")
    return format_html(
        '<img src="{}" width="{}" height="{}" style="object-fit:cover;border-radius:4px" '
        'onerror="this.onerror=null;this.src=\'{}\';" />',
        url,
        width,
        width,
        placeholder_url,
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
# Category tree helpers & filters
# ---------------------------------------------------------------------------


def _get_category_tree_metadata():
    """Build single-query DFS tree order, depth, and full path maps for Category.

    Returns ``(order_map, depth_map, path_map)`` keyed by category PK.
    """
    rows = list(
        Category.objects.order_by("display_order", "name_ar", "pk").values_list(
            "pk", "parent_id", "name_ar"
        )
    )
    by_id = {pk: (parent_id, name_ar) for pk, parent_id, name_ar in rows}
    children_map = {}
    roots = []
    for pk, parent_id, _ in rows:
        if parent_id is None or parent_id not in by_id:
            roots.append(pk)
        else:
            children_map.setdefault(parent_id, []).append(pk)

    order_map = {}
    depth_map = {}
    path_map = {}
    visited = set()

    def _walk(pk, depth, ancestor_names):
        if pk in visited:
            return
        visited.add(pk)
        _, name_ar = by_id[pk]
        chain = [*ancestor_names, name_ar]
        order_map[pk] = len(order_map)
        depth_map[pk] = depth
        path_map[pk] = " / ".join(chain)
        for child_pk in children_map.get(pk, ()):
            _walk(child_pk, depth + 1, chain)

    for root_pk in roots:
        _walk(root_pk, 0, [])

    # Cycle/orphan safety fallback so every row receives deterministic metadata.
    for pk, _, _ in rows:
        if pk not in visited:
            _walk(pk, 0, [])

    return order_map, depth_map, path_map


def _get_descendant_ids(root_id):
    """Return a set containing ``root_id`` and all of its descendant category IDs."""
    children_map = {}
    for cat_id, parent_id in Category.objects.values_list("pk", "parent_id"):
        children_map.setdefault(parent_id, []).append(cat_id)

    excluded = {root_id}
    stack = [root_id]
    while stack:
        current = stack.pop()
        for child_id in children_map.get(current, ()):
            if child_id not in excluded:
                excluded.add(child_id)
                stack.append(child_id)
    return excluded


def _case_from_int_map(mapping, default_value=0):
    """Build a SQL Case/When integer expression from a ``{pk: int}`` mapping."""
    if not mapping:
        return Value(default_value, output_field=IntegerField())
    return Case(
        *[When(pk=pk, then=Value(val)) for pk, val in mapping.items()],
        default=Value(default_value, output_field=IntegerField()),
        output_field=IntegerField(),
    )


class CategoryFolderChoiceField(forms.ModelChoiceField):
    """ModelChoiceField labeling categories with Windows-style folder paths."""

    def __init__(self, *args, path_map=None, **kwargs):
        self._path_map = path_map or {}
        super().__init__(*args, **kwargs)

    def label_from_instance(self, obj):
        path = self._path_map.get(obj.pk)
        if path is None:
            path = obj.full_path
        return f"📁 {path}"


class CategoryNodeTypeFilter(admin.SimpleListFilter):
    title = "نوع التصنيف"
    parameter_name = "node_type"

    def lookups(self, request, model_admin):
        return (
            ("roots", "تصنيفات رئيسية"),
            ("folders", "تصنيفات أب (لها فروع)"),
            ("leaves", "تصنيفات نهائية"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "roots":
            return queryset.filter(parent__isnull=True)
        if value == "folders":
            return queryset.filter(children__isnull=False).distinct()
        if value == "leaves":
            return queryset.filter(children__isnull=True)
        return queryset


class ParentCategoryFilter(admin.SimpleListFilter):
    title = "التصنيف الأب"
    parameter_name = "parent"

    def lookups(self, request, model_admin):
        order_map, _, path_map = _get_category_tree_metadata()
        parent_ids = set(
            Category.objects.filter(children__isnull=False).values_list("pk", flat=True)
        )
        ordered_parent_ids = sorted(
            parent_ids, key=lambda pk: order_map.get(pk, len(order_map))
        )
        choices = [("root", "📁 التصنيفات الرئيسية (بدون أب)")]
        for pk in ordered_parent_ids:
            path = path_map.get(pk)
            if path:
                choices.append((str(pk), f"📁 {path}"))
        return choices

    def queryset(self, request, queryset):
        value = self.value()
        if value == "root":
            return queryset.filter(parent__isnull=True)
        if value:
            try:
                parent_id = int(value)
            except (TypeError, ValueError):
                return queryset.none()
            return queryset.filter(parent_id=parent_id)
        return queryset


class ProductCategoryFilter(admin.SimpleListFilter):
    title = "التصنيف"
    parameter_name = "category"

    def lookups(self, request, model_admin):
        order_map, _, path_map = _get_category_tree_metadata()
        folder_ids = set(
            Category.objects.filter(children__isnull=False).values_list("pk", flat=True)
        )
        ordered_ids = sorted(order_map.keys(), key=lambda pk: order_map[pk])
        choices = []
        for pk in ordered_ids:
            path = path_map.get(pk)
            if not path:
                continue
            icon = "📁" if pk in folder_ids else "📄"
            choices.append((str(pk), f"{icon} {path}"))
        return choices

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        try:
            category_id = int(value)
        except (TypeError, ValueError):
            return queryset.none()
        return queryset.filter(category_id__in=_get_descendant_ids(category_id))


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------


class ChildCategoryInline(admin.TabularInline):
    model = Category
    form = CategoryAdminForm
    fk_name = "parent"
    extra = 0
    fields = ("name_ar", "name_en", "slug", "image", "is_active", "display_order")
    prepopulated_fields: ClassVar[dict[str, tuple[str, ...]]] = {"slug": ("name_en",)}
    show_change_link = True
    verbose_name = "تصنيف فرعي"
    verbose_name_plural = "التصنيفات الفرعية المباشرة"


@admin.register(Category)
class CategoryAdmin(_SafeImageUploadAdminMixin, _ImagePreviewAdminMixin, admin.ModelAdmin):
    form = CategoryAdminForm
    list_display = (
        "image_preview",
        "tree_name",
        "node_type_badge",
        "parent",
        "children_count",
        "products_count",
        "is_active",
        "display_order",
    )
    list_display_links = ("image_preview", "tree_name")
    list_editable = ("is_active", "display_order")
    list_filter = (CategoryNodeTypeFilter, ParentCategoryFilter, "is_active")
    search_fields = ("name_ar", "name_en", "slug")
    prepopulated_fields: ClassVar[dict[str, tuple[str, ...]]] = {"slug": ("name_en",)}
    inlines = (ChildCategoryInline,)
    readonly_fields = _ImagePreviewAdminMixin.readonly_fields + (
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            "المعلومات الأساسية",
            {
                "fields": (
                    "parent",
                    ("name_ar", "name_en"),
                    "slug",
                    "image",
                    "image_preview",
                )
            },
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

    def get_queryset(self, request):
        order_map, depth_map, _ = _get_category_tree_metadata()
        qs = (
            self.model._default_manager.get_queryset()
            .select_related("parent")
            .annotate(
                _children_count=Count("children", distinct=True),
                _products_count=Count("products", distinct=True),
                _tree_order=_case_from_int_map(order_map, default_value=len(order_map)),
                _tree_depth=_case_from_int_map(depth_map, default_value=0),
            )
        )
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs

    def get_ordering(self, request):
        return ("_tree_order", "display_order", "name_ar")

    def _get_current_object_id(self, request):
        current_obj = getattr(request, "_current_category_obj", None)
        if current_obj is not None and current_obj.pk is not None:
            return current_obj.pk
        resolver_match = getattr(request, "resolver_match", None)
        if resolver_match:
            object_id = resolver_match.kwargs.get("object_id")
            if object_id is not None:
                try:
                    return int(object_id)
                except (TypeError, ValueError):
                    return None
        return None

    def get_form(self, request, obj=None, change=False, **kwargs):
        previous = getattr(request, "_current_category_obj", None)
        request._current_category_obj = obj
        try:
            return super().get_form(request, obj=obj, change=change, **kwargs)
        finally:
            if previous is None:
                if hasattr(request, "_current_category_obj"):
                    delattr(request, "_current_category_obj")
            else:
                request._current_category_obj = previous

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "parent":
            order_map, _, path_map = _get_category_tree_metadata()
            qs = (
                Category.objects.filter(products__isnull=True)
                .annotate(
                    _tree_order=_case_from_int_map(
                        order_map, default_value=len(order_map)
                    )
                )
                .order_by("_tree_order", "display_order", "name_ar")
            )
            current_id = self._get_current_object_id(request)
            if current_id is not None:
                qs = qs.exclude(pk__in=_get_descendant_ids(current_id))
            kwargs["queryset"] = qs
            kwargs["form_class"] = CategoryFolderChoiceField
            field = super().formfield_for_foreignkey(db_field, request, **kwargs)
            field._path_map = path_map
            field.empty_label = "— تصنيف رئيسي (المستوى الأعلى) —"
            field.help_text = (
                "اتركه فارغاً ليكون تصنيفاً رئيسياً. "
                "لا يمكن اختيار تصنيف يحتوي على منتجات كأب."
            )
            return field
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_inline_instances(self, request, obj=None):
        if obj is not None and obj.products.exists():
            return []
        return super().get_inline_instances(request, obj)

    def get_search_results(self, request, queryset, search_term):
        queryset, may_have_duplicates = super().get_search_results(
            request, queryset, search_term
        )
        if (
            request.GET.get("model_name") == "product"
            and request.GET.get("field_name") == "category"
        ):
            queryset = queryset.filter(children__isnull=True)
        return queryset, may_have_duplicates

    @admin.display(description="التصنيف (شجرة المجلدات)", ordering="_tree_order")
    def tree_name(self, obj):
        depth = getattr(obj, "_tree_depth", None)
        if depth is None:
            depth = obj.depth
        children_count = getattr(obj, "_children_count", None)
        if children_count is None:
            children_count = 0 if obj.is_leaf else obj.children.count()

        is_folder = children_count > 0
        icon = "📁" if is_folder else "📄"
        indent_px = depth * 22
        connector = (
            format_html(
                '<span style="color:#9ca3af;font-family:monospace;">{}</span>',
                "↳",
            )
            if depth > 0
            else ""
        )
        weight = "600" if is_folder else "400"
        subtitle = (
            format_html(
                ' <span style="color:#6b7280;font-weight:400;font-size:11px;">({})</span>',
                obj.name_en,
            )
            if obj.name_en
            else ""
        )
        return format_html(
            '<span style="display:inline-flex;align-items:center;gap:6px;'
            'margin-inline-start:{}px;font-weight:{};">'
            "{}<span>{}</span><span>{}{}</span></span>",
            indent_px,
            weight,
            connector,
            icon,
            obj.name_ar,
            subtitle,
        )

    @admin.display(description="النوع", ordering="_children_count")
    def node_type_badge(self, obj):
        children_count = getattr(obj, "_children_count", None)
        if children_count is None:
            children_count = 0 if obj.is_leaf else obj.children.count()

        if children_count > 0 and obj.parent_id is None:
            label, bg, fg = "مجلد رئيسي", "#dbeafe", "#1e40af"
        elif children_count > 0:
            label, bg, fg = "مجلد فرعي", "#fef3c7", "#92400e"
        else:
            label, bg, fg = "تصنيف نهائي", "#d1fae5", "#065f46"

        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:999px;'
            'font-size:11px;font-weight:600;background:{};color:{};white-space:nowrap;">'
            "{}</span>",
            bg,
            fg,
            label,
        )

    @admin.display(description="الفروع", ordering="_children_count")
    def children_count(self, obj):
        count = getattr(obj, "_children_count", None)
        if count is None:
            count = obj.children.count()
        if count > 0:
            return format_html(
                '<a href="?parent={}" style="font-weight:600;">{}</a>',
                obj.pk,
                count,
            )
        return format_html('<span style="color:#9ca3af;">{}</span>', 0)

    @admin.display(description="المنتجات", ordering="_products_count")
    def products_count(self, obj):
        count = getattr(obj, "_products_count", None)
        if count is None:
            count = obj.products.count()
        if count > 0:
            url = reverse("admin:catalog_product_changelist")
            return format_html(
                '<a href="{}?category={}" style="font-weight:600;">{}</a>',
                url,
                obj.pk,
                count,
            )
        return format_html('<span style="color:#9ca3af;">{}</span>', 0)

# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------


@admin.register(Product)
class ProductAdmin(_SafeImageUploadAdminMixin, _ImagePreviewAdminMixin, admin.ModelAdmin):
    form = ProductAdminForm
    list_display = (
        "image_preview",
        "name_ar",
        "name_en",
        "category_path",
        "price_sar",
        "is_active",
        "created_at",
    )
    list_display_links = ("image_preview", "name_ar")
    list_filter = ("is_active", ProductCategoryFilter)
    list_select_related = ("category", "category__parent", "category__parent__parent")
    search_fields = ("name_ar", "name_en", "description_ar", "description_en")
    prepopulated_fields: ClassVar[dict[str, tuple[str, ...]]] = {"slug": ("name_en",)}
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

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "category":
            order_map, _, path_map = _get_category_tree_metadata()
            qs = (
                Category.leaf_queryset()
                .annotate(
                    _tree_order=_case_from_int_map(
                        order_map, default_value=len(order_map)
                    )
                )
                .order_by("_tree_order", "display_order", "name_ar")
            )
            kwargs["queryset"] = qs
            kwargs["form_class"] = CategoryFolderChoiceField
            field = super().formfield_for_foreignkey(db_field, request, **kwargs)
            field._path_map = path_map
            field.help_text = "يمكن إضافة المنتج إلى التصنيفات النهائية (الورقية) فقط."
            return field
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="مسار التصنيف", ordering="category__name_ar")
    def category_path(self, obj):
        if not obj.category_id:
            return "-"
        return f"📁 {obj.category.full_path}"


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
