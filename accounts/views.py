from django.contrib import messages
from django.contrib.auth import login as django_login, logout as django_logout
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .models import User

# Number of failed login attempts allowed before throttling
MAX_LOGIN_ATTEMPTS = 5
# Throttle reset time in seconds
LOGIN_ATTEMPT_TIMEOUT = 300  # 5 minutes


def _authenticate(identifier: str, password: str) -> User | None:
    """
    Authenticate using email or username (case-insensitive).
    Uses Django's built-in password check which automatically
    upgrades the hash if needed.
    """
    user = User.objects.filter(
        Q(email__iexact=identifier) | Q(username__iexact=identifier)
    ).first()

    if user and user.is_active and user.check_password(password):
        return user
    return None


@require_http_methods(["GET", "POST"])
def register(request):
    if request.method == "GET":
        return render(request, "register.html")

    email = request.POST.get("email", "").strip()
    password = request.POST.get("password", "")
    password2 = request.POST.get("password2", "")
    username = request.POST.get("username", "").strip()
    full_name = request.POST.get("full_name", "").strip() or None

    # Basic required field check
    if not email or not password or not username:
        return render(
            request,
            "register.html",
            {"error": "All required fields must be filled."},
            status=400,
        )

    # Check that passwords match
    if password != password2:
        return render(
            request,
            "register.html",
            {"error": "Passwords do not match."},
            status=400,
        )

    # Validate password strength using Django's built-in validators
    try:
        validate_password(password, user=None)
    except ValidationError as e:
        return render(
            request,
            "register.html",
            {"error": e.messages},
            status=400,
        )

    # Check for existing user
    if User.objects.filter(email__iexact=email).exists():
        return render(
            request,
            "register.html",
            {"error": "User already exists."},
            status=400,
        )

    # Create user and log them in
    user = User.objects.create_user(
        email=email, password=password, username=username, full_name=full_name
    )
    django_login(request, user)
    return redirect("home")


@require_http_methods(["GET", "POST"])
def login(request):
    if request.method == "GET":
        return render(request, "login.html")

    identifier = request.POST.get("email", "").strip()
    password = request.POST.get("password", "")
    client_ip = request.META.get("REMOTE_ADDR", "")
    cache_key = f"login_attempts_{identifier}_{client_ip}"

    # Rate limiting: check number of failed attempts
    attempts = cache.get(cache_key, 0)
    if attempts >= MAX_LOGIN_ATTEMPTS:
        return render(
            request,
            "login.html",
            {"error": "Too many failed attempts. Try again later."},
            status=429,
        )

    user = _authenticate(identifier, password)

    if not user:
        # Increment failure counter
        cache.set(cache_key, attempts + 1, timeout=LOGIN_ATTEMPT_TIMEOUT)
        return render(
            request,
            "login.html",
            {"error": "Invalid credentials."},
            status=401,
        )

    # Successful login: clear failure counter
    cache.delete(cache_key)

    django_login(request, user)
    return redirect("home")


def logout(request):
    # Place message BEFORE logout so it survives session flush
    messages.info(request, "Logged out.")
    django_logout(request)

    response = redirect("home")
    # Delete custom cookies if they exist – ensure attributes match how they were set
    response.delete_cookie("user_session", path="/")
    response.delete_cookie("admin_session", path="/")
    response.delete_cookie("username", path="/")
    return response