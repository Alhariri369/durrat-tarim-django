from catalog.models import SiteSettings


def site_context(request):
    settings = SiteSettings.get_current()
    user = getattr(request, "store_user", None)
    if user is None:
        user_id = request.session.get("store_user_id")
        if user_id:
            from accounts.models import User

            user = User.objects.filter(id=user_id, is_active=True).first()
            request.store_user = user

    return {
        "site_settings": settings,
        "store_user": user,
        "is_store_authenticated": bool(user),
        "is_store_admin": bool(user and user.role == "admin"),
    }
