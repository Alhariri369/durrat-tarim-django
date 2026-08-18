from django.urls import include, path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    # Keep these before allauth so its canonical URLs use the project's views.
    path("login/", views.login, name="account_login"),
    path("signup/", views.register, name="account_signup"),
    path("logout/", views.logout, name="account_logout"),
    path(
        "register/",
        RedirectView.as_view(pattern_name="account_signup", permanent=False),
    ),
    path("", include("allauth.account.urls")),
]
