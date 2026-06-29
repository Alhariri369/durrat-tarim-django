from django.contrib import admin

from .models import FeaturedProduct, Product, SiteSettings

admin.site.register(Product)
admin.site.register(FeaturedProduct)
admin.site.register(SiteSettings)
