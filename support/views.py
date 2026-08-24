import time
from urllib.parse import urlencode

from allauth.account.models import EmailAddress
from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from catalog.models import StoreSettings

from .forms import ContactForm
from .models import Ticket


def _get_rate_limits():
    """Read the spam limits from the store settings (admin-editable),
    falling back to sane defaults if settings are unavailable."""
    try:
        settings = StoreSettings.get_current()
        cooldown = getattr(settings, "contact_cooldown_seconds", None) or 600
        daily_limit = getattr(settings, "contact_daily_limit", None) or 5
    except Exception:
        cooldown = 600
        daily_limit = 5
    return cooldown, daily_limit


def _rate_limit_ok(request):
    """Anti-spam guard for the contact form: one message per cooldown window
    and at most daily_limit messages per day, tracked per user in the cache.
    Returns (allowed: bool, error_message: str)."""
    cooldown, daily_limit = _get_rate_limits()
    user = request.user
    now = time.time()
    today = timezone.now().date().isoformat()
    cooldown_key = f"contact_cooldown:{user.pk}"
    last_submission = cache.get(cooldown_key)
    if last_submission and (now - last_submission) < cooldown:
        remaining = int(cooldown - (now - last_submission))
        return False, f"يرجى الانتظار {remaining} ثانية قبل إرسال رسالة أخرى."
    daily_key = f"contact_daily:{user.pk}:{today}"
    count = cache.get(daily_key, 0)
    if count >= daily_limit:
        return False, f"لقد تجاوزت الحد اليومي المسموح ({daily_limit} رسائل)."
    return True, ""


def _record_rate_limit(request):
    cooldown, _ = _get_rate_limits()
    user = request.user
    now = time.time()
    today = timezone.now().date().isoformat()
    cache.set(f"contact_cooldown:{user.pk}", now, timeout=cooldown)
    daily_key = f"contact_daily:{user.pk}:{today}"
    try:
        cache.incr(daily_key)
    except ValueError:
        cache.set(daily_key, 1, timeout=86400)


@require_http_methods(["GET", "POST"])
def contact(request):
    if request.method == "GET":
        form = ContactForm()
        return render(
            request,
            "contact.html",
            {
                "form": form,
                "page_title": "اتصل بنا | درة تريم",
            },
        )

    # --- POST: only authenticated users with a verified email may submit ---
    # (logged-out users are sent to login and come back via ?next=).
    if not request.user.is_authenticated:
        login_url = reverse("account_login")
        return redirect(f"{login_url}?{urlencode({'next': request.get_full_path()})}")

    if not EmailAddress.objects.filter(
        user=request.user, verified=True, primary=True
    ).exists():
        messages.error(request, "يجب توثيق بريدك الإلكتروني قبل إرسال رسالة تواصل.")
        return redirect("contact")

    form = ContactForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "contact.html",
            {"form": form, "page_title": "اتصل بنا | درة تريم"},
            status=400,
        )

    ok, rate_error = _rate_limit_ok(request)
    if not ok:
        messages.error(request, rate_error)
        return redirect("contact")

    # Snapshot the user's identity onto the ticket so the record stays
    # meaningful even if they later change their name/email or get deleted.
    cd = form.cleaned_data
    user = request.user
    Ticket.objects.create(
        user=user,
        user_name_snapshot=user.full_name or user.email,
        user_email_snapshot=user.email,
        name=cd["name"],
        phone=cd["phone"],
        subject=cd["subject"],
        details=cd["message"],
    )
    _record_rate_limit(request)
    messages.success(request, "تم إرسال رسالتك بنجاح! سنتواصل معك قريباً.")
    return redirect("contact")
