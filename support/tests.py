from django.test import TestCase
from django.urls import reverse

from accounts.models import User

from .models import Ticket


class SupportViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="secret", full_name="عميل"
        )
        from allauth.account.models import EmailAddress

        EmailAddress.objects.create(
            user=self.user, email=self.user.email, verified=True, primary=True
        )

    def test_contact_form_creates_ticket(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("contact"),
            {
                "name": "عميل كريم",
                "phone": "0500000000",
                "subject": "سؤال",
                "message": "تفاصيل عن المنتج",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Ticket.objects.filter(phone="0500000000").exists())
