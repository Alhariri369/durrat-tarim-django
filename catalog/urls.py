from django.urls import path

from . import views

urlpatterns = [
    path("search/", views.search_products, name="product-search"),
    path("types/", views.get_all_types, name="product-types"),
    path("types/<slug:type_name>/", views.get_type_products, name="product-type"),
    path("items/<int:pk>/", views.product_details, name="product-detail"),
    path(
        "items/<int:pk>/whatsapp/",
        views.product_whatsapp,
        name="product-whatsapp",
    ),
    path("items/<int:pk>/favorite/", views.add_favorite, name="favorite-add"),
    path(
        "items/<int:pk>/unfavorite/",
        views.remove_favorite,
        name="favorite-remove",
    ),
]
