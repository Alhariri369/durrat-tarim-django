"""
Custom authentication views.

These shadow django-allauth's canonical `account_login` / `account_signup`
URLs on purpose: the project wants its own lightweight email+password flow
(plus rate limiting and Arabic messaging) instead of allauth's forms.
Social logins (Google) bypass these views entirely and are handled by
allauth's provider views mounted in `accounts.urls`.
"""

import logging

from allauth.account.models import EmailAddress
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.transaction import Atomic
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .models import User
from .redirects import get_post_login_url

logger = logging.getLogger(__name__)

# Limit failed login attempts per (email, IP) before locking out (see login view).
MAX_LOGIN_ATTEMPTS = 5
LOGIN_ATTEMPT_TIMEOUT = 300


def _authenticate_user(email: str, password: str, request=None) -> User | None:
    # Email IS the username (see accounts.User: username=None). Why? because it's easy and lazy d:
    # Lookup is case-insensitive so "A@B.com" and "a@b.com" hit the same account.
    if not email:
        return None
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        return None
    # authenticate() runs the password through all configured backends.
    authenticated_user = authenticate(request, username=user.email, password=password)
    if authenticated_user and authenticated_user.is_active:
        return authenticated_user
    return None


def _create_account(request, email: str, password: str, full_name: str) -> User:
    # Atomic: the user row and their allauth EmailAddress row must both exist,
    # otherwise account state would be inconsistent (e.g. favorites guard breaks).
    with Atomic(using=None, savepoint=True, durable=False):
        user = User.objects.create_user(
            email=email,
            password=password,
            full_name=full_name,
        )
        # allauth's EmailAddress tracks verification state; the site requires
        # a verified email before favorites / contact work (see _verified_user_redirect).
        email_address = EmailAddress.objects.create(
            user=user, email=user.email, primary=True, verified=False
        )
        email_address.send_confirmation(request, signup=True)
        return user


@require_http_methods(["GET", "POST"])
def register(request):
    # Already logged in? Send them to their destination instead of the form.
    if request.user.is_authenticated:
        return redirect(get_post_login_url(request, request.user))

    if request.method == "GET":
        return render(request, "register.html")

    # --- POST: validate, create the account, then force email verification ---
    # Field names must match the inputs in register.html.
    email = request.POST.get("email", "").strip()
    password = request.POST.get("password1") or request.POST.get("password", "")
    password_confirmation = request.POST.get("password2", password)
    full_name = request.POST.get("full_name", "").strip()
    context = {"email": email, "full_name": full_name}

    # Each failure path re-renders the form with status 400 so the browser
    # doesn't retry the POST, and the user keeps their typed values.
    if not email or not password or not full_name:
        context["error"] = "All required fields must be filled."
        return render(request, "register.html", context, status=400)

    try:
        validate_email(email)
    except ValidationError:
        context["error"] = "Enter a valid email address."
        return render(request, "register.html", context, status=400)

    if password != password_confirmation:
        context["error"] = "Passwords do not match."
        return render(request, "register.html", context, status=400)

    # Run Django's password validators (min length, common passwords, ...)
    # against a throwaway user instance so validation knows the email/name.
    prospective_user = User(email=email, full_name=full_name)
    try:
        validate_password(password, user=prospective_user)
    except ValidationError as exc:
        context["error"] = " ".join(str(message) for message in exc.messages)
        return render(request, "register.html", context, status=400)

    if User.objects.filter(email__iexact=email).exists():
        context["error"] = "User already exists."
        return render(request, "register.html", context, status=400)

    try:
        _create_account(request, email, password, full_name)
    except Exception:
        # Usually a failed verification email — surface it instead of a 500,
        # because the DB row may already be gone (rolled back) or invalid.
        logger.exception("Unable to create account or send verification email")
        context["error"] = "Unable to send the verification email. Please try again."
        return render(request, "register.html", context, status=503)

    messages.info(request, "تم إنشاء حسابك. يرجى التحقق من بريدك الإلكتروني للمتابعة.")
    return redirect("account_email_verification_sent")


@require_http_methods(["GET", "POST"])
def login(request):
    if request.user.is_authenticated:
        return redirect(get_post_login_url(request, request.user))

    if request.method == "GET":
        return render(request, "login.html", {"next": request.GET.get("next", "")})

    email = (request.POST.get("email") or request.POST.get("login", "")).strip()
    password = request.POST.get("password", "")

    # Brute-force protection: at most MAX_LOGIN_ATTEMPTS failures per
    # (email, IP) within LOGIN_ATTEMPT_TIMEOUT seconds. Cache-based so it
    # works on Vercel without a shared state store.
    client_ip = request.META.get("REMOTE_ADDR", "")
    cache_key = f"login_attempts_{email}_{client_ip}"

    attempts = cache.get(cache_key, 0)
    if attempts >= MAX_LOGIN_ATTEMPTS:
        return render(
            request,
            "login.html",
            {"error": "Too many failed attempts. Try again later."},
            status=429,
        )

    user = _authenticate_user(email, password, request=request)
    if not user:
        cache.set(cache_key, attempts + 1, timeout=LOGIN_ATTEMPT_TIMEOUT)
        return render(
            request, "login.html", {"error": "Invalid credentials."}, status=401
        )

    # Success resets the failure counter.
    cache.delete(cache_key)

    # The site requires a verified email before logging in (this also applies
    # to account features like favorites). Remember where they wanted to go.
    if not EmailAddress.objects.filter(user=user, verified=True).exists():
        next_url = request.POST.get("next", "")
        if next_url:
            request.session["favorite_return_url"] = next_url
        messages.error(
            request, "يرجى توثيق بريدك الإلكتروني أولاً. تحقق من صندوق الوارد."
        )
        return redirect("account_email_verification_sent")

    django_login(request, user)
    return redirect(get_post_login_url(request, user))


@require_http_methods(["GET", "POST"])
def logout(request):
    messages.info(request, "Logged out.")
    django_logout(request)
    response = redirect("home")
    # Wipe legacy session cookies from older frontends so stale
    # "logged in" state never leaks after logout.
    response.delete_cookie("user_session", path="/")
    response.delete_cookie("admin_session", path="/")
    response.delete_cookie("username", path="/")
    return response
