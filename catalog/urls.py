from django.urls import path

from . import views

urlpatterns = [
    path("search", views.search_products, name="product-search"),
    path("types", views.get_all_types, name="product-types"),
    path("types/<str:type_name>", views.get_type_products, name="product-type"),
    path("items/<int:pk>", views.product_details, name="product-detail"),
]
