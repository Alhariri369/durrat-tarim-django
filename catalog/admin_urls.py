from django.urls import path

from . import views

urlpatterns = [
    path("", views.admin_dashboard, name="admin-dashboard"),
    path("products", views.admin_products_list, name="admin-products"),
    path("products/new", views.admin_product_create, name="admin-product-create"),
    path("products/<int:pk>/edit", views.admin_product_edit, name="admin-product-edit"),
    path("products/<int:pk>/delete", views.admin_product_delete, name="admin-product-delete"),
    path("settings", views.admin_settings, name="admin-settings"),
    path("login", views.admin_login, name="admin-login"),
    path("logout", views.admin_logout, name="admin-logout"),
]
