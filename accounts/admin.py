from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Restricted user admin: only full_name, is_active and is_staff are editable."""

    list_display = ("email", "full_name", "is_staff", "is_active", "date_created")
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = ("email", "full_name")
    ordering = ("email",)

    # Change form: only these three fields are editable.
    # Email, password, is_superuser, groups and permissions are not shown,
    # so they cannot be changed through the admin.
    fieldsets = (
        (
            "الحساب",
            {"fields": ("full_name", "is_active", "is_staff")},
        ),
        (
            "معلومات للعرض فقط",
            {
                "fields": ("last_login", "date_created"),
                "classes": ("collapse",),
            },
        ),
    )
    readonly_fields = ("last_login", "date_created")

    # New accounts still need an email and a password at creation time.
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "password1", "password2"),
            },
        ),
    )

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change=change, **kwargs)
        if change and "password" in form.base_fields:
            # Remove the password display field entirely on the change form.
            form.base_fields.pop("password", None)
        return form

    def get_urls(self):
        """Remove the password-change URL so existing passwords can't be edited."""
        urls = super().get_urls()
        return [
            url
            for url in urls
            if getattr(url, "name", "") != "auth_user_password_change"
        ]

    def has_change_permission(self, request, obj=None):
        # Only superusers may edit superuser accounts.
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # Only superusers may delete superuser accounts.
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj)
