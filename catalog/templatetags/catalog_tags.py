from django import template

from catalog.currency import format_sar, format_yer

register = template.Library()

register.filter("format_sar", format_sar)
register.filter("format_yer", format_yer)
