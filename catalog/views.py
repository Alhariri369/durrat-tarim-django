from urllib.parse import urlencode

from allauth.account.models import EmailAddress
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import BooleanField, Count, Exists, OuterRef, Q, Value
from django.db.models.expressions import RawSQL
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

HOME_FAQS = [
    {
        "question": "كيف يمكنني طلب منتج؟",
        "answer": (
            'يمكنكِ تصفح المنتجات والضغط على زر "استفسار واتساب" لأي منتج '
            "يعجبكِ، وسيتم توجيهكِ مباشرة إلى محادثة واتساب برسالة جاهزة "
            "تحتوي على تفاصيل القطعة لتأكيد طلبكِ بسرعة."
        ),
    },
    {
        "question": "هل يتوفر التوصيل داخل تريم وسيئون ووادي حضرموت واليمن؟",
        "answer": (
            "نعم، نوفر خدمة التوصيل في تريم وسيئون ومختلف مناطق وادي حضرموت، "
            "مع إمكانية الشحن إلى بقية محافظات اليمن بالتنسيق المباشر عبر واتساب."
        ),
    },
    {
        "question": "ما هي طرق الدفع المتاحة؟",
        "answer": (
            "نقبل الدفع في المحل والتحويل البنكي أو عبر شركات الصرافة المعتمدة. "
            "سيتم توضيح كافة خيارات الدفع المتاحة عند تأكيد طلبكِ عبر واتساب."
        ),
    },
    {
        "question": "هل يمكنني إرجاع أو استبدال المنتج؟",
        "answer": (
            "نعم، نوفر سياسة إرجاع خلال يوم واحد واستبدال خلال 3 أيام من استلام "
            "المنتج، بشرط أن يكون بحالته الأصلية. يرجى التواصل معنا عبر واتساب "
            "لترتيب عملية الإرجاع أو الاستبدال."
        ),
    },
    {
        "question": "بأي عملة تُعرض الأسعار وأين يقع معرض درة تريم؟",
        "answer": (
            "تُعرض جميع الأسعار بالريال السعودي مع ما يعادلها تقريبياً بالريال اليمني "
            "في كل صفحة منتج. يقع معرض درة تريم في سوق الفتح بمدينة تريم، وادي حضرموت، "
            "ونستقبلكِ من السبت إلى الخميس (9:00 صباحاً حتى 9:30 مساءً) والجمعة (4:00 عصراً حتى 10:00 مساءً)."
        ),
    },
    {
        "question": "كيف أضيف منتجات إلى المفضلة؟",
        "answer": (
            "يمكنكِ إنشاء حساب وتوثيق بريدكِ الإلكتروني، ثم الضغط على أيقونة القلب "
            "في أي منتج لحفظه. بعدها يمكنكِ تحديد عدة منتجات من صفحة المفضلة "
            "وإرسالها في استفسار واحد عبر واتساب."
        ),
    },
]


def _og_image_for(request, image_field) -> str:
    """Return an absolute Open Graph image URL, applying ImageKit 1200x630
    JPG transform when hosted on ik.imagekit.io."""
    if not image_field:
        return ""
    url = request.build_absolute_uri(image_field.url)
    if "ik.imagekit.io" in url and "?" not in url:
        return f"{url}?tr=w-1200,h-630,fo-auto,f-jpg,q-85"
    return url

_ACTIVE_CATEGORY_TREE_SQL = """
products.category_id IN (
    WITH RECURSIVE active_categories(id) AS (
        SELECT id FROM categories
        WHERE is_active = TRUE AND parent_id IS NULL
        UNION
        SELECT c.id FROM categories c
        INNER JOIN active_categories ac ON c.parent_id = ac.id
        WHERE c.is_active = TRUE
    )
    SELECT id FROM active_categories
)
"""


class _ActiveCategoryTreeFilter(RawSQL):
    """Conditional RawSQL filter enforcing that a product's entire category
    ancestor chain is active in a single SQL query (SQLite & PostgreSQL)."""

    conditional = True


def _annotated_categories(queryset, active_ids):
    """Annotate categories with effectively-active direct subcategory counts
    and active direct product counts without N+1 queries."""
    return queryset.annotate(
        subcategories_count=Count(
            "children",
            filter=Q(children__id__in=active_ids),
            distinct=True,
        ),
        products_count=Count(
            "products",
            filter=Q(products__is_active=True),
            distinct=True,
        ),
    )


def _public_products(user=None, active_category_ids=None):
    """Base queryset for every storefront view: only active products in
    effectively-active categories (entire ancestor chain active), with
    favorite counts and the viewer's favorite flag annotated in one query."""
    if active_category_ids is not None:
        products = Product.objects.filter(
            is_active=True,
            category_id__in=active_category_ids,
        ).select_related("category")
    else:
        products = Product.objects.filter(
            _ActiveCategoryTreeFilter(_ACTIVE_CATEGORY_TREE_SQL, []),
            is_active=True,
        ).select_related("category")
    products = products.annotate(favorite_count=Count("favorites", distinct=True))
    if user is not None and user.is_authenticated:
        # is_favorite=True when the current user has this product in favorites.
        products = products.annotate(
            is_favorite=Exists(
                Favorite.objects.filter(user=user, product_id=OuterRef("pk"))
            )
        )
    else:
        # Anonymous users get a constant False so templates can use the
        # attribute unconditionally.
        products = products.annotate(
            is_favorite=Value(False, output_field=BooleanField())
        )
    return products


def _paginate(request, queryset):
    page_obj = Paginator(queryset, PRODUCTS_PER_PAGE).get_page(request.GET.get("page"))
    # Keep every other query param (q, etc.) when building pagination links.
    query = request.GET.copy()
    query.pop("page", None)
    return page_obj, query.urlencode()


def _safe_return_url(request, fallback="home"):
    """Resolve a `next` param without allowing open redirects: only URLs on
    this host (and https when the request was https) are honored."""
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return reverse(fallback)


def _verified_user_redirect(request):
    """Gate for account features (favorites): redirects anonymous users to
    login and unverified users to email verification, remembering where they
    came from so they land back here afterwards. Returns None when OK."""
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
    """Landing page: latest products, active root categories and the featured
    slider (FeaturedProduct rows flagged in the admin)."""
    active_ids = Category.active_category_ids()
    products = list(
        _public_products(request.user, active_category_ids=active_ids).order_by(
            "-created_at", "-id"
        )[:LATEST_PRODUCTS_LIMIT]
    )
    categories = _annotated_categories(
        Category.objects.filter(parent__isnull=True, id__in=active_ids),
        active_ids,
    ).order_by("display_order", "name_ar")
    featured = list(
        FeaturedProduct.objects.filter(
            is_active=True,
            product__is_active=True,
            product__category_id__in=active_ids,
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
            "faqs": HOME_FAQS,
            "page_title": "درة تريم | قطع عرائسية وأقمشة وأزياء راقية في تريم وحضرموت",
            "meta_description": (
                "درة تريم: قطع عرائسية وأقمشة فاخرة وأزياء راقية في تريم وسيئون "
                "ووادي حضرموت واليمن بأسعار بالريال السعودي واليمني وطلب مباشر عبر واتساب."
            ),
            "hero": (
                "catalog/partials/featured_slider.html"
                if featured
                else "catalog/partials/empty_hero.html"
            ),
        },
    )


def all_products(request):
    """Indexable public catalog listing (/products/) with pagination."""
    products = _public_products(request.user).order_by("-created_at", "-id")
    page_obj, pagination_query = _paginate(request, products)
    page_suffix = f" - صفحة {page_obj.number}" if page_obj.number > 1 else ""
    return render(
        request,
        "search.html",
        {
            "is_catalog_index": True,
            "products": page_obj.object_list,
            "page_obj": page_obj,
            "pagination_query": pagination_query,
            "query": "",
            "empty_message": "لا توجد منتجات متاحة حالياً.",
            "search_heading": "جميع المنتجات",
            "page_title": f"جميع المنتجات{page_suffix} | درة تريم",
            "meta_description": (
                "تصفحي جميع القطع العرائسية والأقمشة والأزياء الراقية المتوفرة في درة تريم "
                "بوادي حضرموت واليمن مع الأسعار بالريال السعودي واليمني."
            ),
            "breadcrumbs": [
                ("الرئيسية", "/"),
                ("جميع المنتجات", reverse("product-list")),
            ],
        },
    )


def search_products(request):
    raw_query = request.GET.get("q", request.GET.get("product_desc", "")).strip()
    # normalize_arabic() maps alef/hamza/yaa variants so "ابيض" finds "أبيض"
    # etc. — both the raw and normalized forms are searched.
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
    context = {
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
            else "البحث في المنتجات | درة تريم"
        ),
        "meta_description": (
            "ابحثي في منتجات درة تريم من القطع العرائسية والأقمشة والأزياء الراقية "
            "وتصفحي الأسعار بالريال السعودي واليمني."
        ),
        "robots_content": "noindex,follow",
        "breadcrumbs": [
            ("الرئيسية", "/"),
            ("البحث", reverse("product-search")),
        ],
    }
    if not raw_query:
        context["canonical_url"] = request.build_absolute_uri(reverse("product-list"))
    return render(request, "search.html", context)


def get_all_types(request):
    active_ids = Category.active_category_ids()
    categories = _annotated_categories(
        Category.objects.filter(parent__isnull=True, id__in=active_ids),
        active_ids,
    ).order_by("display_order", "name_ar")
    return render(
        request,
        "types.html",
        {
            "categories": categories,
            "page_title": "التصنيفات | درة تريم",
            "meta_description": (
                "تصفحي تصنيفات القطع العرائسية والأقمشة والأزياء الراقية في درة تريم "
                "بتريم وسيئون ووادي حضرموت واليمن."
            ),
            "breadcrumbs": [
                ("الرئيسية", "/"),
                ("التصنيفات", reverse("product-types")),
            ],
        },
    )


def get_type_products(request, type_name):
    active_ids = Category.active_category_ids()
    category = get_object_or_404(
        Category.objects.select_related("parent"),
        pk__in=active_ids,
        slug=type_name,
    )
    breadcrumbs = [
        ("الرئيسية", "/"),
        ("التصنيفات", reverse("product-types")),
    ] + [
        (c.name_ar, reverse("product-type", args=[c.slug]))
        for c in category.get_path_categories()
    ]
    is_folder = category.children.exists()
    if is_folder:
        subcategories = list(
            _annotated_categories(
                Category.objects.filter(parent=category, id__in=active_ids),
                active_ids,
            ).order_by("display_order", "name_ar")
        )
        products = []
        page_obj = None
        pagination_query = ""
        meta_description = (
            f"تصفحي الأقسام الفرعية في {category.name_ar} من درة تريم: "
            "قطع عرائسية وأقمشة وأزياء راقية في تريم ووادي حضرموت واليمن."
        )
    else:
        subcategories = []
        products_qs = _public_products(
            request.user, active_category_ids=active_ids
        ).filter(category=category)
        page_obj, pagination_query = _paginate(
            request, products_qs.order_by("-created_at", "-id")
        )
        products = page_obj.object_list
        meta_description = (
            f"تصفحي تشكيلة {category.name_ar} من درة تريم في تريم وسيئون ووادي حضرموت "
            "والأسعار بالريال السعودي واليمني."
        )

    page_suffix = (
        f" - صفحة {page_obj.number}" if page_obj and page_obj.number > 1 else ""
    )
    return render(
        request,
        "type_products.html",
        {
            "is_folder": is_folder,
            "subcategories": subcategories,
            "products": products,
            "page_obj": page_obj,
            "pagination_query": pagination_query,
            "category": category,
            "empty_message": "لا توجد منتجات متاحة في هذا التصنيف حاليا.",
            "page_title": f"{category.name_ar}{page_suffix} | درة تريم",
            "meta_description": meta_description,
            "og_image": _og_image_for(request, category.image),
            "breadcrumbs": breadcrumbs,
        },
    )


def product_details(request, pk):
    product = get_object_or_404(_public_products(request.user), pk=pk)
    breadcrumbs = (
        [
            ("الرئيسية", "/"),
            ("التصنيفات", reverse("product-types")),
        ]
        + [
            (c.name_ar, reverse("product-type", args=[c.slug]))
            for c in product.category.get_path_categories()
        ]
        + [(product.name_ar, reverse("product-detail", args=[product.pk]))]
    )
    fallback_desc = (
        f"{product.name_ar} من درة تريم. اطلبي عبر واتساب مع التوصيل في تريم وسيئون "
        "ووادي حضرموت وكافة مناطق اليمن."
    )
    return render(
        request,
        "product_details.html",
        {
            "product": product,
            "page_title": f"{product.name_ar} | درة تريم",
            "meta_description": (product.description_ar or fallback_desc)[:160],
            # Product-specific Open Graph data for social share previews.
            "og_type": "product",
            "og_image": _og_image_for(request, product.image),
            "breadcrumbs": breadcrumbs,
        },
    )


def product_whatsapp(request, pk):
    product = get_object_or_404(_public_products(), pk=pk)
    # Broadcast a signal so analytics code (or future listeners) can count
    # WhatsApp clicks without modifying this view. No receiver is wired yet —
    # tests connect to it to verify the click fires.
    product_whatsapp_clicked.send_robust(
        sender=Product, request=request, product=product
    )
    # Redirect to wa.me with a pre-filled message about this product.
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
            "robots_content": "noindex,nofollow",
        },
    )


@require_POST
def favorites_whatsapp(request):
    auth_redirect = _verified_user_redirect(request)
    if auth_redirect:
        return auth_redirect
    # Parse the checked product IDs from the form, dedupe (preserving order)
    # and cap at MAX_FAVORITES_PER_MESSAGE to keep the WhatsApp message sane.
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
