from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


def get_post_login_url(request, user) -> str:
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        request.session.pop("favorite_return_url", None)
        return next_url

    favorite_return_url = request.session.pop("favorite_return_url", None)
    if favorite_return_url and url_has_allowed_host_and_scheme(
        favorite_return_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return favorite_return_url

    # allauth stores the `next` query param of social logins in the session.
    social_next_url = request.session.pop("socialaccount_next_url", None)
    if social_next_url and url_has_allowed_host_and_scheme(
        social_next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return social_next_url

    if user.is_staff:
        return reverse("dashboard")

    return reverse("home")
