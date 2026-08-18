from django.contrib import admin

from .models import Ticket


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "phone",
        "subject",
        "status",
        "user_link",
        "assigned_to",
        "creation_date",
    )
    list_filter = ("status", "creation_date")
    list_editable = ("status", "assigned_to")
    search_fields = ("name", "phone", "subject", "details", "user_email_snapshot")
    readonly_fields = (
        "creation_date",
        "date_edited",
        "user",
        "user_name_snapshot",
        "user_email_snapshot",
    )
    autocomplete_fields = ("user", "assigned_to")
    fieldsets = (
        (None, {"fields": ("name", "phone", "subject", "details")}),
        ("حالة التذكرة", {"fields": ("status", "assigned_to")}),
        ("المستخدم", {"fields": ("user", "user_name_snapshot", "user_email_snapshot")}),
        ("التواريخ", {"fields": ("creation_date", "date_edited")}),
    )

    @admin.display(description="المستخدم", ordering="user__email")
    def user_link(self, obj):
        if obj.user:
            return obj.user.email
        return "-"
