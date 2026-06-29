from django.test import TestCase
from django.urls import reverse

from .models import Ticket


class SupportViewsTests(TestCase):
    def test_contact_form_creates_ticket(self):
        response = self.client.post(
            reverse("contact"),
            {
                "name": "عميل",
                "phone": "0500000000",
                "subject": "سؤال",
                "message": "تفاصيل",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Ticket.objects.filter(phone="0500000000").exists())
