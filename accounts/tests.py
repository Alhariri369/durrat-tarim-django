import re
from types import SimpleNamespace
from unittest.mock import patch

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .adapter import AccountAdapter, SocialAccountAdapter
from .models import User
from .redirects import get_post_login_url


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountViewsTests(TestCase):
    password = "Zebra-Planet-8462"

    def create_verified_user(self, *, is_staff=False):
        user = User.objects.create_user(
            email="user@example.com",
            password=self.password,
            full_name="Test User",
            is_staff=is_staff,
        )
        EmailAddress.objects.create(
            user=user, email=user.email, verified=True, primary=True
        )
        return user

    def test_signup_creates_user_and_sends_verification_email(self):
        response = self.client.post(
            reverse("account_signup"),
            {
                "email": "user@example.com",
                "full_name": "Test User",
                "password1": self.password,
                "password2": self.password,
            },
        )

        self.assertRedirects(
            response,
            reverse("account_email_verification_sent"),
            fetch_redirect_response=False,
        )
        user = User.objects.get(email="user@example.com")
        self.assertEqual(user.full_name, "Test User")
        self.assertTrue(
            EmailAddress.objects.filter(
                user=user, email=user.email, primary=True, verified=False
            ).exists()
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["user@example.com"])

    def test_email_confirmation_logs_user_in_and_redirects_home(self):
        self.client.post(
            reverse("account_signup"),
            {
                "email": "user@example.com",
                "full_name": "Test User",
                "password1": self.password,
                "password2": self.password,
            },
        )
        match = re.search(
            r"http://testserver(/auth/confirm-email/\S+)", mail.outbox[0].body
        )
        if match is None:
            self.fail("Verification email did not contain a confirmation URL")
        confirmation_path = match.group(1)

        confirmation_page = self.client.get(confirmation_path)
        self.assertEqual(confirmation_page.status_code, 200)
        response = self.client.post(confirmation_path, follow=True)

        email_address = EmailAddress.objects.get(email="user@example.com")
        self.assertTrue(email_address.verified)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(response.request["PATH_INFO"], reverse("home"))

    def test_signup_rejects_mismatched_passwords(self):
        response = self.client.post(
            reverse("account_signup"),
            {
                "email": "user@example.com",
                "full_name": "Test User",
                "password1": self.password,
                "password2": "Different-Password-159",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Passwords do not match", status_code=400)
        self.assertFalse(User.objects.filter(email="user@example.com").exists())

    def test_login_redirects_verified_customer_home(self):
        self.create_verified_user()

        response = self.client.post(
            reverse("account_login"),
            {"login": "user@example.com", "password": self.password},
        )

        self.assertRedirects(response, reverse("home"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_redirects_staff_to_dashboard(self):
        self.create_verified_user(is_staff=True)

        response = self.client.post(
            reverse("account_login"),
            {"email": "user@example.com", "password": self.password},
        )

        self.assertRedirects(response, reverse("dashboard"))

    def test_login_honors_safe_next_url(self):
        self.create_verified_user()
        target = reverse("contact")

        response = self.client.post(
            reverse("account_login"),
            {
                "email": "user@example.com",
                "password": self.password,
                "next": target,
            },
        )

        self.assertRedirects(response, target, fetch_redirect_response=False)

    def test_login_ignores_external_next_url(self):
        self.create_verified_user()

        response = self.client.post(
            reverse("account_login"),
            {
                "email": "user@example.com",
                "password": self.password,
                "next": "https://example.net/phishing",
            },
        )

        self.assertRedirects(response, reverse("home"))

    def test_login_rejects_unverified_email(self):
        user = User.objects.create_user(
            email="user@example.com",
            password=self.password,
            full_name="Test User",
        )
        EmailAddress.objects.create(
            user=user, email=user.email, verified=False, primary=True
        )

        response = self.client.post(
            reverse("account_login"),
            {"email": "user@example.com", "password": self.password},
        )

        self.assertRedirects(
            response,
            reverse("account_email_verification_sent"),
            fetch_redirect_response=False,
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_register_url_redirects_to_canonical_signup(self):
        response = self.client.get("/auth/register/")

        self.assertRedirects(
            response, reverse("account_signup"), fetch_redirect_response=False
        )

    def test_signup_rejects_duplicate_email(self):
        User.objects.create_user(email="user@example.com", password=self.password)

        response = self.client.post(
            reverse("account_signup"),
            {
                "email": "USER@example.com",
                "full_name": "Test User",
                "password1": self.password,
                "password2": self.password,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            User.objects.filter(email__iexact="user@example.com").count(), 1
        )


class AccessControlTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.anonymous_urls = [
            reverse("home"),
            reverse("account_login"),
            reverse("contact"),
        ]
        cls.staff_only_urls = [
            "/admin/",
            "/dashboard/",
        ]

    def test_anonymous_can_access_public_pages(self):
        for url in self.anonymous_urls:
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])

    def test_anonymous_redirected_from_staff_pages(self):
        for url in self.staff_only_urls:
            response = self.client.get(url)
            self.assertIn(response.status_code, [302, 403])

    def test_regular_user_cannot_access_staff_pages(self):
        user = User.objects.create_user(email="user@example.com", password="secret")
        self.client.force_login(user)
        for url in self.staff_only_urls:
            response = self.client.get(url)
            self.assertIn(response.status_code, [302, 403])

    def test_staff_user_can_access_dashboard_and_admin(self):
        user = User.objects.create_user(
            email="staff@example.com", password="secret", is_staff=True
        )
        self.client.force_login(user)
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_access_dashboard_and_admin(self):
        user = User.objects.create_superuser(
            email="super@example.com", password="secret", full_name="Super"
        )
        self.client.force_login(user)
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class OpenRedirectAndAuthEdgeCaseTests(TestCase):
    password = "Zebra-Planet-8462"

    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            email="customer@example.com",
            password=self.password,
            full_name="Customer User",
        )
        EmailAddress.objects.create(
            user=self.user, email=self.user.email, verified=True, primary=True
        )
        self.staff = User.objects.create_user(
            email="staff-edge@example.com",
            password=self.password,
            full_name="Staff User",
            is_staff=True,
        )
        EmailAddress.objects.create(
            user=self.staff, email=self.staff.email, verified=True, primary=True
        )

    def tearDown(self):
        cache.clear()

    def test_login_blocks_open_redirect_variants(self):
        malicious_targets = [
            "//evil.example.com/phish",
            "https://evil.example.com/login",
            "http://evil.example.com/",
            "javascript:alert(1)",
            "///evil.example.com",
        ]
        for bad_next in malicious_targets:
            with self.subTest(next_url=bad_next):
                self.client.logout()
                response = self.client.post(
                    reverse("account_login"),
                    {
                        "email": self.user.email,
                        "password": self.password,
                        "next": bad_next,
                    },
                )
                self.assertRedirects(response, reverse("home"))

    def test_authenticated_user_on_login_and_signup_blocks_external_next(self):
        self.client.force_login(self.user)

        resp_login_bad = self.client.get(
            f"{reverse('account_login')}?next=https://evil.example.com"
        )
        self.assertRedirects(resp_login_bad, reverse("home"))

        resp_login_safe = self.client.get(
            f"{reverse('account_login')}?next={reverse('contact')}"
        )
        self.assertRedirects(
            resp_login_safe, reverse("contact"), fetch_redirect_response=False
        )

        resp_signup_bad = self.client.get(
            f"{reverse('account_signup')}?next=//evil.example.com"
        )
        self.assertRedirects(resp_signup_bad, reverse("home"))

    def test_get_post_login_url_session_fallbacks_and_open_redirect_guards(self):
        # Safe favorite_return_url is honored and popped
        req = self.factory.get("/auth/login/")
        req.session = {"favorite_return_url": "/favorites/"}
        self.assertEqual(get_post_login_url(req, self.user), "/favorites/")
        self.assertNotIn("favorite_return_url", req.session)

        # Unsafe favorite_return_url is ignored and popped
        req_bad_fav = self.factory.get("/auth/login/")
        req_bad_fav.session = {"favorite_return_url": "https://evil.example.com/steal"}
        self.assertEqual(get_post_login_url(req_bad_fav, self.user), reverse("home"))
        self.assertNotIn("favorite_return_url", req_bad_fav.session)

        # Safe socialaccount_next_url is honored and popped
        req_social = self.factory.get("/auth/google/login/callback/")
        req_social.session = {"socialaccount_next_url": "/contact/"}
        self.assertEqual(get_post_login_url(req_social, self.user), "/contact/")
        self.assertNotIn("socialaccount_next_url", req_social.session)

        # Unsafe socialaccount_next_url falls back to dashboard for staff
        req_social_bad = self.factory.get("/auth/google/login/callback/")
        req_social_bad.session = {"socialaccount_next_url": "//evil.example.com"}
        self.assertEqual(
            get_post_login_url(req_social_bad, self.staff), reverse("dashboard")
        )
        self.assertNotIn("socialaccount_next_url", req_social_bad.session)

        # Explicit safe ?next overrides and clears favorite_return_url
        req_priority = self.factory.post("/auth/login/", {"next": "/contact/"})
        req_priority.session = {"favorite_return_url": "/favorites/"}
        self.assertEqual(get_post_login_url(req_priority, self.user), "/contact/")
        self.assertNotIn("favorite_return_url", req_priority.session)

    def test_login_case_insensitive_email_and_brute_force_lockout(self):
        # 5 failed attempts return 401; 6th returns 429
        for _ in range(5):
            resp = self.client.post(
                reverse("account_login"),
                {"email": self.user.email, "password": "wrong-password"},
            )
            self.assertEqual(resp.status_code, 401)

        locked = self.client.post(
            reverse("account_login"),
            {"email": self.user.email, "password": self.password},
        )
        self.assertEqual(locked.status_code, 429)

        # After cache clears, uppercase email succeeds
        cache.clear()
        ok = self.client.post(
            reverse("account_login"),
            {"email": self.user.email.upper(), "password": self.password},
        )
        self.assertRedirects(ok, reverse("home"))

    def test_inactive_user_cannot_log_in(self):
        inactive = User.objects.create_user(
            email="inactive@example.com",
            password=self.password,
            is_active=False,
        )
        EmailAddress.objects.create(
            user=inactive, email=inactive.email, verified=True, primary=True
        )

        resp = self.client.post(
            reverse("account_login"),
            {"email": inactive.email, "password": self.password},
        )
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unverified_login_stores_next_in_session(self):
        unverified = User.objects.create_user(
            email="unverified-next@example.com", password=self.password
        )
        EmailAddress.objects.create(
            user=unverified, email=unverified.email, verified=False, primary=True
        )

        resp = self.client.post(
            reverse("account_login"),
            {
                "email": unverified.email,
                "password": self.password,
                "next": "/favorites/",
            },
        )
        self.assertRedirects(
            resp,
            reverse("account_email_verification_sent"),
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client.session.get("favorite_return_url"), "/favorites/")

    def test_register_validation_errors_and_email_failure_rollback(self):
        # Missing required fields
        r_missing = self.client.post(reverse("account_signup"), {"email": ""})
        self.assertEqual(r_missing.status_code, 400)

        # Invalid email
        r_email = self.client.post(
            reverse("account_signup"),
            {
                "email": "not-an-email",
                "full_name": "Test",
                "password1": self.password,
                "password2": self.password,
            },
        )
        self.assertEqual(r_email.status_code, 400)

        # Weak password
        r_weak = self.client.post(
            reverse("account_signup"),
            {
                "email": "weak@example.com",
                "full_name": "Test",
                "password1": "123",
                "password2": "123",
            },
        )
        self.assertEqual(r_weak.status_code, 400)

        # Email send failure rolls back user & EmailAddress and returns 503
        with (
            patch.object(
                EmailAddress,
                "send_confirmation",
                side_effect=RuntimeError("SMTP unavailable"),
            ),
            self.assertLogs("accounts.views", level="ERROR"),
        ):
            r_fail = self.client.post(
                reverse("account_signup"),
                {
                    "email": "rollback@example.com",
                    "full_name": "Rollback User",
                    "password1": self.password,
                    "password2": self.password,
                },
            )
        self.assertEqual(r_fail.status_code, 503)
        self.assertFalse(User.objects.filter(email="rollback@example.com").exists())
        self.assertFalse(
            EmailAddress.objects.filter(email="rollback@example.com").exists()
        )

    def test_logout_clears_session_and_legacy_cookies(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("account_logout"))

        self.assertRedirects(response, reverse("home"))
        self.assertNotIn("_auth_user_id", self.client.session)
        for cookie_name in ("user_session", "admin_session", "username"):
            self.assertIn(cookie_name, response.cookies)
            self.assertEqual(response.cookies[cookie_name]["max-age"], 0)


class AccountAndSocialAdapterTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            email="adapter-user@example.com",
            password="Zebra-Planet-8462",
            full_name="Adapter User",
        )
        self.staff = User.objects.create_user(
            email="adapter-staff@example.com",
            password="Zebra-Planet-8462",
            full_name="Adapter Staff",
            is_staff=True,
        )

    def test_account_adapter_get_login_redirect_url(self):
        adapter = AccountAdapter()

        req_safe = self.factory.get("/auth/login/?next=/contact/")
        req_safe.user = self.user
        req_safe.session = {}
        self.assertEqual(adapter.get_login_redirect_url(req_safe), "/contact/")

        req_unsafe = self.factory.get("/auth/login/?next=https://evil.example.com")
        req_unsafe.user = self.staff
        req_unsafe.session = {}
        self.assertEqual(
            adapter.get_login_redirect_url(req_unsafe), reverse("dashboard")
        )

    def test_social_adapter_populate_user_sets_full_name(self):
        adapter = SocialAccountAdapter()
        req = self.factory.get("/auth/google/login/callback/")

        # Both first_name and last_name
        user_both = User()
        sociallogin = SimpleNamespace(user=user_both)
        populated = adapter.populate_user(
            req,
            sociallogin,
            {
                "email": "sara@example.com",
                "first_name": "Sara",
                "last_name": "Ali",
            },
        )
        self.assertEqual(populated.full_name, "Sara Ali")

        # Only first_name
        user_first = User()
        sociallogin_first = SimpleNamespace(user=user_first)
        populated_first = adapter.populate_user(
            req,
            sociallogin_first,
            {"email": "mona@example.com", "first_name": "Mona", "last_name": ""},
        )
        self.assertEqual(populated_first.full_name, "Mona")

        # Empty name fields leave full_name empty without error
        user_empty = User()
        sociallogin_empty = SimpleNamespace(user=user_empty)
        populated_empty = adapter.populate_user(
            req,
            sociallogin_empty,
            {"email": "noname@example.com"},
        )
        self.assertEqual(populated_empty.full_name, "")

    def test_user_manager_validation_guards(self):
        with self.assertRaisesMessage(ValueError, "Email is required"):
            User.objects.create_user(email="", password="secret")

        with self.assertRaisesMessage(ValueError, "Superuser must have is_staff=True."):
            User.objects.create_superuser(
                email="bad-super1@example.com", password="secret", is_staff=False
            )

        with self.assertRaisesMessage(
            ValueError, "Superuser must have is_superuser=True."
        ):
            User.objects.create_superuser(
                email="bad-super2@example.com", password="secret", is_superuser=False
            )

    def test_google_trusted_and_site_verification_mandatory_settings(self):
        self.assertEqual(settings.ACCOUNT_EMAIL_VERIFICATION, "mandatory")
        self.assertEqual(settings.SOCIALACCOUNT_EMAIL_VERIFICATION, "none")
        self.assertTrue(
            settings.SOCIALACCOUNT_PROVIDERS["google"].get("VERIFIED_EMAIL")
        )

    def test_pre_social_login_verifies_existing_user_only_for_verified_google(self):
        adapter = SocialAccountAdapter()
        req = self.factory.get("/auth/google/login/callback/")

        # Superuser created via createsuperuser has no EmailAddress row yet
        superuser = User.objects.create_superuser(
            email="super@example.com",
            password="Zebra-Planet-8462",
            full_name="Super User",
        )
        sociallogin_super = SimpleNamespace(
            account=SimpleNamespace(
                provider="google", extra_data={"email": superuser.email, "email_verified": True}
            ),
            email_addresses=[
                SimpleNamespace(email=superuser.email, verified=True)
            ],
            user=superuser,
            is_existing=True,
        )
        adapter.pre_social_login(req, sociallogin_super)
        super_ea = EmailAddress.objects.get(user=superuser, email=superuser.email)
        self.assertTrue(super_ea.verified)
        self.assertTrue(super_ea.primary)

        # Registered user with unverified EmailAddress gets marked verified on Google login
        unverified_user = User.objects.create_user(
            email="existing@example.com",
            password="Zebra-Planet-8462",
            full_name="Existing User",
        )
        ea_unverified = EmailAddress.objects.create(
            user=unverified_user,
            email=unverified_user.email,
            verified=False,
            primary=True,
        )
        sociallogin_match = SimpleNamespace(
            account=SimpleNamespace(
                provider="google",
                extra_data={"email": unverified_user.email, "email_verified": True},
            ),
            email_addresses=[],
            user=User(email=unverified_user.email),
            is_existing=False,
        )
        adapter.pre_social_login(req, sociallogin_match)
        ea_unverified.refresh_from_db()
        self.assertTrue(ea_unverified.verified)

        # Unverified Google payload OR non-Google provider does NOT auto-verify
        other_user = User.objects.create_user(
            email="notverified@example.com",
            password="Zebra-Planet-8462",
            full_name="Other User",
        )
        ea_other = EmailAddress.objects.create(
            user=other_user, email=other_user.email, verified=False, primary=True
        )
        adapter.pre_social_login(
            req,
            SimpleNamespace(
                account=SimpleNamespace(
                    provider="google",
                    extra_data={"email": other_user.email, "email_verified": False},
                ),
                email_addresses=[],
                user=User(email=other_user.email),
                is_existing=False,
            ),
        )
        ea_other.refresh_from_db()
        self.assertFalse(ea_other.verified)

        adapter.pre_social_login(
            req,
            SimpleNamespace(
                account=SimpleNamespace(
                    provider="github",
                    extra_data={"email": other_user.email, "email_verified": True},
                ),
                email_addresses=[],
                user=User(email=other_user.email),
                is_existing=False,
            ),
        )
        ea_other.refresh_from_db()
        self.assertFalse(ea_other.verified)

    def test_google_only_user_without_password_gets_401_on_password_login(self):
        google_user = User.objects.create_user(
            email="google-only@example.com",
            password=None,
            full_name="Google Only",
        )
        EmailAddress.objects.create(
            user=google_user, email=google_user.email, verified=True, primary=True
        )
        self.assertFalse(google_user.has_usable_password())

        resp = self.client.post(
            reverse("account_login"),
            {"email": google_user.email, "password": "anything-at-all"},
        )
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_styled_allauth_templates_render_rtl_without_raw_menu(self):
        resp_sent = self.client.get(reverse("account_email_verification_sent"))
        self.assertEqual(resp_sent.status_code, 200)
        self.assertContains(resp_sent, 'dir="rtl"')
        self.assertContains(resp_sent, "glass-card")
        self.assertNotContains(resp_sent, "<strong>قائمة:</strong>")

        resp_confirm = self.client.get(
            reverse("account_confirm_email", args=["invalid-key-123"])
        )
        self.assertEqual(resp_confirm.status_code, 200)
        self.assertContains(resp_confirm, 'dir="rtl"')
        self.assertContains(resp_confirm, "glass-card")
        self.assertNotContains(resp_confirm, "<strong>قائمة:</strong>")
