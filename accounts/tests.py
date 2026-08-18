import re

from allauth.account.models import EmailAddress
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import User


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
