from allauth.account.signals import email_confirmed
from django.conf import settings
from django.contrib.auth import login
from django.dispatch import receiver


@receiver(email_confirmed)
def login_user_after_email_confirmation(request, email_address, **kwargs):
    user = email_address.user
    if (
        settings.ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION
        and request is not None
        and not request.user.is_authenticated
        and user.is_active
    ):
        login(
            request,
            user,
            backend="allauth.account.auth_backends.AuthenticationBackend",
        )
