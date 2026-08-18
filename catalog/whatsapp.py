from urllib.parse import urlencode

from django.dispatch import Signal
from django.urls import reverse

from .currency import format_sar, format_yer

WHATSAPP_NUMBER = "967783278181"
MAX_FAVORITES_PER_MESSAGE = 20
MAX_WHATSAPP_MESSAGE_LENGTH = 3500

product_whatsapp_clicked = Signal()


def canonical_product_url(request, product):
    return request.build_absolute_uri(
        reverse("product-detail", kwargs={"pk": product.pk})
    )


def product_message(request, product):
    return "\n".join(
        [
            "السلام عليكم، أود الاستفسار عن هذا المنتج:",
            product.name_ar,
            f"السعر: {format_sar(product.price_sar)} (حوالي {format_yer(product.price_sar)})",
            canonical_product_url(request, product),
        ]
    )


def favorites_message(request, products):
    lines = ["السلام عليكم، أود الاستفسار عن المنتجات التالية:"]
    included = 0
    for index, product in enumerate(products[:MAX_FAVORITES_PER_MESSAGE], start=1):
        item_lines = [
            f"{index}. {product.name_ar}",
            f"{format_sar(product.price_sar)} (حوالي {format_yer(product.price_sar)})",
            canonical_product_url(request, product),
        ]
        candidate = "\n".join([*lines, *item_lines])
        if len(candidate) > MAX_WHATSAPP_MESSAGE_LENGTH:
            break
        lines.extend(item_lines)
        included += 1
    return "\n".join(lines), included


def whatsapp_url(message):
    return f"https://wa.me/{WHATSAPP_NUMBER}?{urlencode({'text': message})}"
