from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from .redirects import get_post_login_url


class AccountAdapter(DefaultAccountAdapter):
    """Email+password flow redirects (see accounts.views.login/register)."""

    def get_login_redirect_url(self, request):
        return get_post_login_url(request, getattr(request, "user"))


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Google (and other social) logins.

    allauth already maps the provider's common fields onto first_name and
    last_name in DefaultSocialAccountAdapter.populate_user(). This adapter
    additionally fills the project's custom `full_name` field so the
    social-signed-up user isn't left with an empty display name.

    Note: `populate_user()` runs ONLY when a brand-new user is being created
    from a social login (first sign-in with that provider account). It does
    not run on subsequent logins.
    """

    def populate_user(self, request, sociallogin, data):
        # super() handles first_name/last_name (and email). Reading them back
        # from the user object is the most robust: it works regardless of the
        # exact provider key names (e.g. Google sends given_name/family_name,
        # which allauth converts to first_name/last_name before calling us).
        user = super().populate_user(request, sociallogin, data)
        full_name = " ".join(part for part in (user.first_name, user.last_name) if part)
        if full_name:
            user.full_name = full_name
        return user
