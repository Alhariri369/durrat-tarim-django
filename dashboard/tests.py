from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import Category, Product
from support.models import Ticket


class DashboardAccessControlTests(TestCase):
    def setUp(self):
        self.url = reverse("dashboard")
        self.regular_user = User.objects.create_user(
            email="customer@example.com",
            password="Strong-Password-123!",
            full_name="عميل عادي",
            is_staff=False,
        )
        self.staff_user = User.objects.create_user(
            email="staff@example.com",
            password="Strong-Password-123!",
            full_name="موظف",
            is_staff=True,
        )
        self.superuser = User.objects.create_superuser(
            email="admin@example.com",
            password="Strong-Password-123!",
            full_name="مدير النظام",
        )

    def test_anonymous_user_redirected_to_admin_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response["Location"])
        self.assertIn("next=/dashboard/", response["Location"])

    def test_non_staff_user_blocked_from_dashboard(self):
        self.client.force_login(self.regular_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response["Location"])

    def test_inactive_staff_user_blocked_from_dashboard(self):
        inactive_staff = User.objects.create_user(
            email="inactive-staff@example.com",
            password="Strong-Password-123!",
            full_name="موظف معطل",
            is_staff=True,
            is_active=False,
        )
        self.client.force_login(inactive_staff)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response["Location"])

    def test_staff_user_can_access_dashboard(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/index.html")

    def test_superuser_can_access_dashboard(self):
        self.client.force_login(self.superuser)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/index.html")


class DashboardMetricsTests(TestCase):
    def setUp(self):
        self.url = reverse("dashboard")
        self.staff_user = User.objects.create_user(
            email="staff-metrics@example.com",
            password="Strong-Password-123!",
            full_name="موظف",
            is_staff=True,
        )
        self.client.force_login(self.staff_user)

    def test_empty_database_metrics_are_zero(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_products"], 0)
        self.assertEqual(response.context["total_categories"], 0)
        self.assertEqual(response.context["total_tickets"], 0)
        self.assertEqual(response.context["pending_tickets"], 0)

    def test_summary_metrics_match_database_counts(self):
        active_cat = Category.objects.create(
            name_ar="أقمشة فاخرة",
            slug="luxury-fabrics",
            is_active=True,
        )
        inactive_cat = Category.objects.create(
            name_ar="تصنيف مؤرشف",
            slug="archived-cat",
            is_active=False,
        )

        Product.objects.create(
            name_ar="منتج أول",
            slug="product-1",
            category=active_cat,
            price_sar=Decimal("150.00"),
            image="products/p1.png",
            is_active=True,
        )
        Product.objects.create(
            name_ar="منتج ثاني",
            slug="product-2",
            category=active_cat,
            price_sar=Decimal("220.00"),
            image="products/p2.png",
            is_active=True,
        )
        Product.objects.create(
            name_ar="منتج غير نشط",
            slug="product-3",
            category=inactive_cat,
            price_sar=Decimal("90.00"),
            image="products/p3.png",
            is_active=False,
        )

        Ticket.objects.create(
            name="عميل أول",
            phone="0500000001",
            subject="استفسار جديد 1",
            details="تفاصيل التذكرة الأولى",
            status=Ticket.Status.NEW,
        )
        Ticket.objects.create(
            name="عميل ثاني",
            phone="0500000002",
            subject="استفسار جديد 2",
            details="تفاصيل التذكرة الثانية",
            status=Ticket.Status.NEW,
        )
        Ticket.objects.create(
            name="عميل ثالث",
            phone="0500000003",
            subject="قيد المعالجة",
            details="تفاصيل التذكرة الثالثة",
            status=Ticket.Status.IN_PROGRESS,
        )
        Ticket.objects.create(
            name="عميل رابع",
            phone="0500000004",
            subject="مكتمل",
            details="تفاصيل التذكرة الرابعة",
            status=Ticket.Status.COMPLETED,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_products"], 3)
        self.assertEqual(response.context["total_categories"], 2)
        self.assertEqual(response.context["total_tickets"], 4)
        self.assertEqual(response.context["pending_tickets"], 2)
