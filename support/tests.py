from unittest.mock import patch

from allauth.account.models import EmailAddress
from django.core.cache import cache
from django.core.mail.backends.base import BaseEmailBackend
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .models import Ticket
from .views import _get_rate_limits


class FailingEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise RuntimeError("Simulated email transport failure")


class SupportViewsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("contact")
        self.user = User.objects.create_user(
            email="test@example.com", password="secret", full_name="عميل"
        )
        EmailAddress.objects.create(
            user=self.user, email=self.user.email, verified=True, primary=True
        )
        self.valid_payload = {
            "name": "عميل كريم",
            "phone": "0500000000",
            "subject": "سؤال عن الطلب",
            "message": "تفاصيل كاملة عن المنتج المطلوب",
        }

    def tearDown(self):
        cache.clear()

    def test_contact_get_renders_form_for_anonymous_user(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_anonymous_post_redirects_to_login_with_next(self):
        response = self.client.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response["Location"])
        self.assertIn("next=%2Fcontact%2F", response["Location"])
        self.assertEqual(Ticket.objects.count(), 0)

    def test_unverified_user_cannot_submit_ticket(self):
        unverified_user = User.objects.create_user(
            email="unverified@example.com",
            password="secret",
            full_name="مستخدم غير موثق",
        )
        EmailAddress.objects.create(
            user=unverified_user,
            email=unverified_user.email,
            verified=False,
            primary=True,
        )
        self.client.force_login(unverified_user)

        response = self.client.post(self.url, self.valid_payload, follow=True)

        self.assertRedirects(response, self.url)
        self.assertEqual(Ticket.objects.count(), 0)
        msgs = [m.message for m in response.context["messages"]]
        self.assertTrue(any("توثيق" in msg for msg in msgs))

    def test_contact_form_creates_ticket(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, self.valid_payload)

        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        ticket = Ticket.objects.get(phone="0500000000")
        self.assertEqual(ticket.user, self.user)
        self.assertEqual(ticket.user_name_snapshot, "عميل")
        self.assertEqual(ticket.user_email_snapshot, "test@example.com")
        self.assertEqual(ticket.subject, "سؤال عن الطلب")
        self.assertEqual(ticket.details, "تفاصيل كاملة عن المنتج المطلوب")
        self.assertEqual(ticket.status, Ticket.Status.NEW)

    def test_blank_subject_defaults_to_general_inquiry(self):
        self.client.force_login(self.user)
        payload = {**self.valid_payload, "subject": "   "}

        response = self.client.post(self.url, payload)

        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        ticket = Ticket.objects.get(phone="0500000000")
        self.assertEqual(ticket.subject, "استفسار عام")

    def test_missing_required_fields_returns_400(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {})

        self.assertEqual(response.status_code, 400)
        form = response.context["form"]
        self.assertIn("name", form.errors)
        self.assertIn("phone", form.errors)
        self.assertIn("message", form.errors)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_invalid_name_phone_and_short_message_return_400(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            {
                "name": "John Doe",
                "phone": "12345",
                "subject": "سؤال",
                "message": "قصير",
            },
        )

        self.assertEqual(response.status_code, 400)
        form = response.context["form"]
        self.assertIn("name", form.errors)
        self.assertIn("phone", form.errors)
        self.assertIn("message", form.errors)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_oversized_inputs_are_rejected_with_400(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            {
                "name": "أ" * 201,
                "phone": "05" + "0" * 25,
                "subject": "م" * 501,
                "message": "تفاصيل كافية وطويلة للاستفسار عن الطلب",
            },
        )

        self.assertEqual(response.status_code, 400)
        form = response.context["form"]
        self.assertIn("name", form.errors)
        self.assertIn("phone", form.errors)
        self.assertIn("subject", form.errors)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_honeypot_website_field_rejects_spam_with_400(self):
        self.client.force_login(self.user)
        payload = {**self.valid_payload, "website": "https://spam.example"}

        response = self.client.post(self.url, payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("website", response.context["form"].errors)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_cooldown_rate_limit_blocks_immediate_resubmission(self):
        self.client.force_login(self.user)
        first = self.client.post(self.url, self.valid_payload)
        self.assertEqual(first.status_code, 302)

        second = self.client.post(self.url, self.valid_payload, follow=True)
        self.assertRedirects(second, self.url)
        self.assertEqual(Ticket.objects.count(), 1)
        msgs = [m.message for m in second.context["messages"]]
        self.assertTrue(any("الانتظار" in msg for msg in msgs))

    def test_daily_rate_limit_blocks_excess_submissions(self):
        self.client.force_login(self.user)
        today = timezone.now().date().isoformat()
        cache.set(f"contact_daily:{self.user.pk}:{today}", 5, timeout=3600)

        response = self.client.post(self.url, self.valid_payload, follow=True)

        self.assertRedirects(response, self.url)
        self.assertEqual(Ticket.objects.count(), 0)
        msgs = [m.message for m in response.context["messages"]]
        self.assertTrue(any("الحد اليومي" in msg for msg in msgs))

    @override_settings(EMAIL_BACKEND="support.tests.FailingEmailBackend")
    def test_contact_submission_safe_when_email_backend_fails(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Ticket.objects.count(), 1)

    @patch("support.views.StoreSettings.get_current", side_effect=RuntimeError("db down"))
    def test_rate_limits_fall_back_safely_when_store_settings_fail(self, _mock):
        self.assertEqual(_get_rate_limits(), (600, 5))

        self.client.force_login(self.user)
        response = self.client.post(self.url, self.valid_payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Ticket.objects.count(), 1)
