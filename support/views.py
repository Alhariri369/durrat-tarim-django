from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from catalog.utils import normalize_arabic
from .models import Ticket


@require_http_methods(["GET", "POST"])
def contact(request):
    if request.method == "GET":
        return render(request, "contact.html")

    Ticket.objects.create(
        name=normalize_arabic(request.POST.get("name")),
        phone=request.POST.get("phone", "").strip(),
        subject=request.POST.get("subject", "").strip() or "استفسار عام",
        details=request.POST.get("message", "").strip(),
    )
    return render(
        request,
        "contact.html",
        {"success": "تم إرسال رسالتك بنجاح! سنتواصل معك قريباً."},
    )
