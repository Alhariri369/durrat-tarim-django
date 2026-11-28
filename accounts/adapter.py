from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from .models import User
from .redirects import get_post_login_url


class AccountAdapter(DefaultAccountAdapter):
    """Email+password flow redirects (see accounts.views.login/register)."""

    def get_login_redirect_url(self, request):
        return get_post_login_url(request, request.user)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Google (and other social) logins.

    allauth already maps the provider's common fields onto first_name and
    last_name in DefaultSocialAccountAdapter.populate_user(). This adapter
    additionally fills the project's custom `full_name` field so the
    social-signed-up user isn't left with an empty display name, and trusts
    Google-verified emails for matching pre-existing users.

    Note: `populate_user()` runs ONLY when a brand-new user is being created
    from a social login (first sign-in with that provider account). It does
    not run on subsequent logins.
    """

    def pre_social_login(self, request, sociallogin):
        super().pre_social_login(request, sociallogin)
        if getattr(sociallogin.account, "provider", None) != "google":
            return

        extra_data = getattr(sociallogin.account, "extra_data", None) or {}
        email_addresses = getattr(sociallogin, "email_addresses", None) or []
        is_verified = extra_data.get("email_verified") is True or any(
            getattr(ea, "verified", False) for ea in email_addresses
        )
        if not is_verified:
            return

        email = next(
            (
                ea.email
                for ea in email_addresses
                if getattr(ea, "verified", False) and getattr(ea, "email", "")
            ),
            "",
        )
        if not email:
            email = getattr(sociallogin.user, "email", "") or extra_data.get("email", "")
        email = (email or "").strip()
        if not email:
            return

        if sociallogin.is_existing and getattr(sociallogin.user, "pk", None):
            existing_user = sociallogin.user
        else:
            existing_user = User.objects.filter(email__iexact=email).first()

        if not existing_user:
            return

        email_obj = EmailAddress.objects.filter(
            user=existing_user, email__iexact=email
        ).first()
        if email_obj:
            if not email_obj.verified:
                email_obj.verified = True
                email_obj.save(update_fields=["verified"])
        else:
            has_primary = EmailAddress.objects.filter(
                user=existing_user, primary=True
            ).exists()
            EmailAddress.objects.create(
                user=existing_user,
                email=existing_user.email or email,
                verified=True,
                primary=not has_primary,
            )

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
