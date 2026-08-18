from urllib.parse import urlencode

from allauth.account.models import EmailAddress
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import BooleanField, Count, Exists, OuterRef, Q, Value
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import Category, Favorite, FeaturedProduct, Product
from .utils import normalize_arabic
from .whatsapp import (
    MAX_FAVORITES_PER_MESSAGE,
    favorites_message,
    product_message,
    product_whatsapp_clicked,
    whatsapp_url,
)

PRODUCTS_PER_PAGE = 12
LATEST_PRODUCTS_LIMIT = 8


def _public_products(user=None):
    products = Product.objects.filter(
        is_active=True, category__is_active=True
    ).select_related("category")
    products = products.annotate(favorite_count=Count("favorites", distinct=True))
    if user is not None and user.is_authenticated:
        products = products.annotate(
            is_favorite=Exists(
                Favorite.objects.filter(user=user, product_id=OuterRef("pk"))
            )
        )
    else:
        products = products.annotate(
            is_favorite=Value(False, output_field=BooleanField())
        )
    return products


def _paginate(request, queryset):
    page_obj = Paginator(queryset, PRODUCTS_PER_PAGE).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return page_obj, query.urlencode()


def _safe_return_url(request, fallback="home"):
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return reverse(fallback)


def _verified_user_redirect(request):
    return_url = (
        request.get_full_path()
        if request.method == "GET" and not request.GET.get("next")
        else _safe_return_url(request)
    )
    if not request.user.is_authenticated:
        request.session["favorite_return_url"] = return_url
        return redirect(f"{reverse('account_login')}?{urlencode({'next': return_url})}")
    if not EmailAddress.objects.filter(user=request.user, verified=True).exists():
        request.session["favorite_return_url"] = return_url
        messages.error(request, "يرجى توثيق بريدك الإلكتروني لاستخدام المفضلة.")
        return redirect(
            f"{reverse('account_email_verification_sent')}?"
            f"{urlencode({'next': return_url})}"
        )
    return None


def health(request):
    return JsonResponse({"status": "online", "store": "durrat_tarim"})


def home(request):
    products = list(
        _public_products(request.user).order_by("-created_at", "-id")[
            :LATEST_PRODUCTS_LIMIT
        ]
    )
    categories = Category.objects.filter(is_active=True).order_by(
        "display_order", "name_ar"
    )
    featured = list(
        FeaturedProduct.objects.filter(
            is_active=True,
            product__is_active=True,
            product__category__is_active=True,
        )
        .select_related("product", "product__category")
        .order_by("display_order", "id")
    )
    favorite_ids = set()
    favorite_counts = {}
    if featured:
        product_ids = [item.product_id for item in featured]
        favorite_counts = dict(
            Favorite.objects.filter(product_id__in=product_ids)
            .values_list("product_id")
            .annotate(total=Count("id"))
        )
        if request.user.is_authenticated:
            favorite_ids = set(
                Favorite.objects.filter(
                    user=request.user, product_id__in=product_ids
                ).values_list("product_id", flat=True)
            )
    for index, item in enumerate(featured):
        item.product.is_favorite = item.product_id in favorite_ids
        item.product.favorite_count = favorite_counts.get(item.product_id, 0)
        item.hidden = "" if index == 0 else "hidden"
        item.aria_hidden = "false" if index == 0 else "true"
        item.aria_current = "true" if index == 0 else "false"

    return render(
        request,
        "index.html",
        {
            "products": products,
            "categories": categories,
            "featured": featured,
            "page_title": "درة تريم | أزياء وعبايات",
            "hero": (
                "catalog/partials/featured_slider.html"
                if featured
                else "catalog/partials/empty_hero.html"
            ),
        },
    )


def search_products(request):
    raw_query = request.GET.get("q", request.GET.get("product_desc", "")).strip()
    query = normalize_arabic(raw_query)
    products = _public_products(request.user)
    if raw_query:
        products = products.filter(
            Q(name_ar__icontains=raw_query)
            | Q(description_ar__icontains=raw_query)
            | Q(name_ar__icontains=query)
            | Q(description_ar__icontains=query)
        )
    page_obj, pagination_query = _paginate(
        request, products.order_by("-created_at", "-id")
    )
    return render(
        request,
        "search.html",
        {
            "products": page_obj.object_list,
            "page_obj": page_obj,
            "pagination_query": pagination_query,
            "query": raw_query,
            "empty_message": "لم نجد منتجات مطابقة لبحثك.",
            "search_heading": (
                f"نتائج البحث عن «{raw_query}»" if raw_query else "جميع المنتجات"
            ),
            "page_title": (
                f"نتائج البحث عن {raw_query} | درة تريم"
                if raw_query
                else "جميع المنتجات | درة تريم"
            ),
            "meta_description": "ابحثي في منتجات درة تريم وتصفحي الأسعار بالريال السعودي واليمني.",
        },
    )


def get_all_types(request):
    categories = Category.objects.filter(is_active=True).order_by(
        "display_order", "name_ar"
    )
    return render(
        request,
        "types.html",
        {
            "categories": categories,
            "page_title": "التصنيفات | درة تريم",
            "meta_description": "تصفحي تصنيفات الأزياء والعبايات في درة تريم.",
        },
    )


def get_type_products(request, type_name):
    category = get_object_or_404(Category, is_active=True, slug=type_name)
    products = _public_products(request.user).filter(category=category)
    page_obj, pagination_query = _paginate(
        request, products.order_by("-created_at", "-id")
    )
    return render(
        request,
        "type_products.html",
        {
            "products": page_obj.object_list,
            "page_obj": page_obj,
            "pagination_query": pagination_query,
            "category": category,
            "empty_message": "لا توجد منتجات متاحة في هذا التصنيف حاليا.",
            "page_title": f"{category.name_ar} | درة تريم",
            "meta_description": f"تصفحي منتجات {category.name_ar} من درة تريم.",
        },
    )


def product_details(request, pk):
    product = get_object_or_404(_public_products(request.user), pk=pk)
    return render(
        request,
        "product_details.html",
        {
            "product": product,
            "page_title": f"{product.name_ar} | درة تريم",
            "meta_description": (product.description_ar or product.name_ar)[:150],
        },
    )


def product_whatsapp(request, pk):
    product = get_object_or_404(_public_products(), pk=pk)
    product_whatsapp_clicked.send_robust(
        sender=Product, request=request, product=product
    )
    return redirect(whatsapp_url(product_message(request, product)))


@require_POST
def add_favorite(request, pk):
    auth_redirect = _verified_user_redirect(request)
    if auth_redirect:
        return auth_redirect
    product = get_object_or_404(_public_products(), pk=pk)
    _, created = Favorite.objects.get_or_create(user=request.user, product=product)
    if created:
        messages.success(request, "تمت إضافة المنتج إلى المفضلة.")
    else:
        messages.info(request, "المنتج موجود في المفضلة بالفعل.")
    return redirect(_safe_return_url(request))


@require_POST
def remove_favorite(request, pk):
    auth_redirect = _verified_user_redirect(request)
    if auth_redirect:
        return auth_redirect
    deleted, _ = Favorite.objects.filter(user=request.user, product_id=pk).delete()
    if deleted:
        messages.success(request, "تمت إزالة المنتج من المفضلة.")
    else:
        messages.info(request, "المنتج غير موجود في المفضلة.")
    return redirect(_safe_return_url(request, fallback="favorites"))


def favorites(request):
    auth_redirect = _verified_user_redirect(request)
    if auth_redirect:
        return auth_redirect
    products = (
        _public_products(request.user)
        .filter(favorites__user=request.user)
        .order_by("-favorites__created_at", "-favorites__id")
    )
    page_obj, pagination_query = _paginate(request, products)
    return render(
        request,
        "favorites.html",
        {
            "products": page_obj.object_list,
            "page_obj": page_obj,
            "pagination_query": pagination_query,
            "show_selection": True,
            "hide_favorite": True,
            "page_title": "المفضلة | درة تريم",
            "meta_description": "منتجاتك المفضلة في درة تريم.",
        },
    )


@require_POST
def favorites_whatsapp(request):
    auth_redirect = _verified_user_redirect(request)
    if auth_redirect:
        return auth_redirect
    selected_ids = []
    for value in request.POST.getlist("products"):
        try:
            selected_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    selected_ids = list(dict.fromkeys(selected_ids))[:MAX_FAVORITES_PER_MESSAGE]
    products = list(
        _public_products(request.user)
        .filter(id__in=selected_ids, favorites__user=request.user)
        .order_by("id")[:MAX_FAVORITES_PER_MESSAGE]
    )
    if not products:
        messages.error(request, "اختاري منتجا واحدا على الأقل من مفضلتك.")
        return redirect("favorites")
    message, included = favorites_message(request, products)
    if not included:
        messages.error(request, "تعذر إنشاء رسالة ضمن الحد المسموح.")
        return redirect("favorites")
    return redirect(whatsapp_url(message))
