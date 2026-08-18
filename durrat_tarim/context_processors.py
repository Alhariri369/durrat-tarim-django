from django.urls import reverse

from catalog.models import StoreSettings


def site_context(request):
    settings = StoreSettings.get_current()
    user = request.user if request.user.is_authenticated else None

    return {
        "site_settings": settings,
        "store_user": user,
        "is_store_authenticated": bool(user),
        "is_store_admin": bool(user and user.is_staff),
        "account_action_url": reverse("account_logout" if user else "account_login"),
        "account_action_label": "تسجيل الخروج" if user else "تسجيل الدخول",
    }
