from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from catalog.models import Category, Product
from support.models import Ticket


@staff_member_required
def dashboard(request):
    """Simple store dashboard: staff-only summary counts shown in
    templates/dashboard/index.html. Just a landing page — actual content
    management happens in Django's /admin/."""
    context = {
        "total_products": Product.objects.count(),
        "total_categories": Category.objects.count(),
        "total_tickets": Ticket.objects.count(),
        "pending_tickets": Ticket.objects.filter(status=Ticket.Status.NEW).count(),
    }
    return render(request, "dashboard/index.html", context)
