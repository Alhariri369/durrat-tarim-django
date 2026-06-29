from django.db import models
from django.utils import timezone


class Product(models.Model):
    name = models.CharField(max_length=200, db_index=True)
    img_url = models.CharField(max_length=500, blank=True, null=True)
    type = models.CharField(max_length=200, db_index=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    creation_date = models.DateTimeField(default=timezone.now)
    date_edited = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "products"
        ordering = ["id"]

    def save(self, *args, **kwargs):
        self.date_edited = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class FeaturedProduct(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, db_column="product_id")
    display_order = models.IntegerField(default=0)
    creation_date = models.DateTimeField(default=timezone.now)
    date_edited = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "featured_products"
        ordering = ["display_order", "id"]


class SiteSettings(models.Model):
    light_color_primary = models.CharField(max_length=50, default="#30669c")
    light_color_secondary = models.CharField(max_length=50, default="#08121b")
    light_color_accent = models.CharField(max_length=50, default="#e0801f")
    light_color_background = models.CharField(max_length=50, default="#f6f1ee")
    light_color_surface = models.CharField(max_length=50, default="#ffffff")
    dark_color_primary = models.CharField(max_length=50, default="#39f2f9")
    dark_color_secondary = models.CharField(max_length=50, default="#e0ebe7")
    dark_color_accent = models.CharField(max_length=50, default="#e7994b")
    dark_color_background = models.CharField(max_length=50, default="#08121b")
    dark_color_surface = models.CharField(max_length=50, default="#0c1927")

    class Meta:
        db_table = "site_settings"

    @classmethod
    def get_current(cls):
        settings = cls.objects.first()
        if settings:
            return settings
        return cls.objects.create()
