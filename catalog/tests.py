from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from .models import Product, SiteSettings


class CatalogViewsTests(TestCase):
    def test_home_and_search_render_products(self):
        Product.objects.create(name="عباية", type="عبايات", price="120.00", description="ناعم")

        home = self.client.get(reverse("home"))
        search = self.client.get(reverse("product-search"), {"product_desc": "عباية"})

        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "عباية")
        self.assertEqual(search.status_code, 200)
        self.assertContains(search, "عباية")

    def test_admin_session_can_create_product(self):
        admin = User.objects.create_user(
            email="admin@example.com",
            username="admin",
            password="secret",
            role=User.Role.ADMIN,
        )
        session = self.client.session
        session["admin_user_id"] = str(admin.id)
        session["store_user_id"] = str(admin.id)
        session.save()

        response = self.client.post(
            reverse("admin-product-create"),
            {"name": "فستان", "type": "فساتين", "price": "250.00", "description": "جديد"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Product.objects.filter(name="فستان").exists())

    def test_site_settings_update(self):
        admin = User.objects.create_user(
            email="admin@example.com",
            username="admin",
            password="secret",
            role=User.Role.ADMIN,
        )
        SiteSettings.get_current()
        session = self.client.session
        session["admin_user_id"] = str(admin.id)
        session["store_user_id"] = str(admin.id)
        session.save()

        response = self.client.post(
            reverse("admin-settings"),
            {
                "light_color_primary": "#111111",
                "light_color_secondary": "#222222",
                "light_color_accent": "#333333",
                "light_color_background": "#444444",
                "light_color_surface": "#555555",
                "dark_color_primary": "#666666",
                "dark_color_secondary": "#777777",
                "dark_color_accent": "#888888",
                "dark_color_background": "#999999",
                "dark_color_surface": "#aaaaaa",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(SiteSettings.get_current().light_color_primary, "#111111")
