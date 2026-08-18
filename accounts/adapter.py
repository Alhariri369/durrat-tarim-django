from allauth.account.adapter import DefaultAccountAdapter

from .redirects import get_post_login_url


class AccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        return get_post_login_url(request, getattr(request, "user"))
