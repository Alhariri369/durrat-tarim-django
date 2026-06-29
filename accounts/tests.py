from django.test import TestCase
from django.urls import reverse

from .models import User


class AccountViewsTests(TestCase):
    def test_register_logs_user_into_session(self):
        response = self.client.post(
            reverse("register"),
            {
                "email": "user@example.com",
                "username": "user",
                "password": "secret",
                "full_name": "Test User",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email="user@example.com").exists())
        self.assertIn("store_user_id", self.client.session)

    def test_login_accepts_created_user(self):
        User.objects.create_user(email="user@example.com", username="user", password="secret")

        response = self.client.post(
            reverse("login"),
            {"email": "user@example.com", "password": "secret"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("store_user_id", self.client.session)
