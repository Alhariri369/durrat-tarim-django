import os
import tempfile
import uuid
from pathlib import Path
from urllib import error, request

from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts.models import User
from accounts.views import _authenticate
from .models import Product, SiteSettings
from .utils import normalize_arabic


DEFAULT_SUPABASE_STORAGE_BUCKET = "product-images"


def _pagination(request):
    try:
        skip = max(int(request.GET.get("skip", 0)), 0)
    except ValueError:
        skip = 0
    try:
        limit = min(max(int(request.GET.get("limit", 20)), 1), 100)
    except ValueError:
        limit = 20
    return skip, limit


def _products_slice(queryset, request):
    skip, limit = _pagination(request)
    return queryset[skip : skip + limit]


def health(request):
    return JsonResponse({"status": "online", "store": "درة تريم"})


def home(request):
    products = _products_slice(Product.objects.filter(is_active=True).order_by("id"), request)
    return render(request, "index.html", {"products": products})


def search_products(request):
    raw_query = request.GET.get("product_desc", "")
    query = normalize_arabic(raw_query)
    products = Product.objects.filter(is_active=True)
    if raw_query or query:
        products = products.filter(
            Q(name__icontains=raw_query)
            | Q(description__icontains=raw_query)
            | Q(name__icontains=query)
            | Q(description__icontains=query)
        )
    products = _products_slice(products.order_by("id"), request)
    return render(request, "search.html", {"products": products, "query": query, "type_name": query})


def get_all_types(request):
    types = Product.objects.filter(is_active=True).exclude(type="").values_list("type", flat=True).distinct()
    return render(request, "types.html", {"types": types})


def get_type_products(request, type_name):
    normalized_type = normalize_arabic(type_name)
    products = _products_slice(
        Product.objects.filter(is_active=True, type=normalized_type).order_by("id"), request
    )
    return render(request, "type_products.html", {"products": products, "type_name": type_name})


def product_details(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    return render(request, "product_details.html", {"product": product})


def _admin_user(request):
    user_id = request.session.get("admin_user_id")
    if not user_id:
        return None
    return User.objects.filter(id=user_id, is_active=True, role=User.Role.ADMIN).first()


def admin_required(view_func):
    def wrapped(request, *args, **kwargs):
        admin = _admin_user(request)
        if not admin:
            return redirect("admin-login")
        request.admin_user = admin
        return view_func(request, *args, **kwargs)

    return wrapped


@admin_required
def admin_dashboard(request):
    return render(
        request,
        "admin/dashboard.html",
        {
            "admin_user": request.admin_user,
            "total_products": Product.objects.count(),
            "total_types": Product.objects.values("type").distinct().count(),
        },
    )


@admin_required
def admin_products_list(request):
    products = Product.objects.order_by("id")[:1000]
    return render(request, "admin/products.html", {"admin_user": request.admin_user, "products": products})


def _save_product_image(image):
    if not image:
        return None

    suffix = Path(image.name).suffix or ".jpg"
    filename = f"{uuid.uuid4().hex}{suffix}"
    storage_path = f"products/{filename}"
    content = b"".join(image.chunks())

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if supabase_url and supabase_key:
        return _upload_product_image_to_supabase(
            storage_path=storage_path,
            content=content,
            content_type=getattr(image, "content_type", None) or "application/octet-stream",
            supabase_url=supabase_url.rstrip("/"),
            supabase_key=supabase_key,
        )

    upload_dir = _writable_upload_dir()
    with (upload_dir / filename).open("wb+") as destination:
        destination.write(content)
    return f"{settings.MEDIA_URL}products/{filename}"


def _upload_product_image_to_supabase(storage_path, content, content_type, supabase_url, supabase_key):
    bucket = os.getenv("SUPABASE_STORAGE_BUCKET", DEFAULT_SUPABASE_STORAGE_BUCKET)
    upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{storage_path}"
    upload_request = request.Request(
        upload_url,
        data=content,
        method="POST",
        headers={
            "Authorization": f"Bearer {supabase_key}",
            "apikey": supabase_key,
            "Content-Type": content_type,
            "x-upsert": "true",
        },
    )
    try:
        with request.urlopen(upload_request, timeout=15):
            pass
    except error.URLError as exc:
        raise RuntimeError("Unable to upload product image to Supabase Storage") from exc

    public_base_url = os.getenv(
        "PRODUCT_IMAGE_BASE_URL",
        f"{supabase_url}/storage/v1/object/public/{bucket}",
    )
    return f"{public_base_url.rstrip('/')}/{storage_path}"


def _writable_upload_dir():
    upload_dir = settings.MEDIA_ROOT / "products"
    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
        return upload_dir
    except OSError:
        fallback_dir = Path(tempfile.gettempdir()) / "uploads" / "products"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return fallback_dir


@require_http_methods(["GET", "POST"])
@admin_required
def admin_product_create(request):
    if request.method == "GET":
        return render(
            request,
            "admin/product_form.html",
            {
                "admin_user": request.admin_user,
                "form_action": "/admin/products/new",
                "form_title": "إضافة منتج جديد",
                "submit_label": "حفظ المنتج",
            },
        )

    Product.objects.create(
        name=normalize_arabic(request.POST.get("name")),
        type=normalize_arabic(request.POST.get("type")),
        price=request.POST.get("price") or 0,
        description=request.POST.get("description", ""),
        img_url=_save_product_image(request.FILES.get("img_file")),
    )
    return redirect("admin-products")


@require_http_methods(["GET", "POST"])
@admin_required
def admin_product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "GET":
        return render(
            request,
            "admin/product_form.html",
            {
                "admin_user": request.admin_user,
                "product": product,
                "form_action": f"/admin/products/{product.pk}/edit",
                "form_title": "تعديل المنتج",
                "submit_label": "حفظ التعديلات",
            },
        )

    product.name = normalize_arabic(request.POST.get("name"))
    product.type = normalize_arabic(request.POST.get("type;l    i9ol,."))
    try:
        product.price = float(request.POST.get("price", 0))
    except (ValueError, TypeError):
        product.price = 0
        
    product.description = request.POST.get("description", "")

    img_url = _save_product_image(request.FILES.get("img_file"))
    if img_url:
        product.img_url = img_url

    product.save()
    return redirect("admin-products")


@admin_required
def admin_product_delete(request, pk):
    Product.objects.filter(pk=pk).delete()
    return redirect("admin-products")


@require_http_methods(["GET", "POST"])
@admin_required
def admin_settings(request):
    site_settings = SiteSettings.get_current()
    if request.method == "GET":
        return render(request, "admin/settings.html", {"admin_user": request.admin_user, "site_settings": site_settings})

    fields = [
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
    ]
    for field in fields:
        setattr(site_settings, field, request.POST.get(field, getattr(site_settings, field)))
    site_settings.save(update_fields=fields)
    return redirect("admin-settings")


@require_http_methods(["GET", "POST"])
def admin_login(request):
    if request.method == "GET":
        return render(request, "admin/login.html")

    username = request.POST.get("username", "").strip()
    password = request.POST.get("password", "")
    user = _authenticate(username, password)
    if not user or user.role != User.Role.ADMIN:
        return render(request, "admin/login.html", {"error": "Invalid admin credentials."}, status=401)

    request.session["store_user_id"] = str(user.id)
    request.session["admin_user_id"] = str(user.id)
    return redirect("admin-dashboard")


def admin_logout(request):
    request.session.pop("admin_user_id", None)
    return redirect("admin-login")
