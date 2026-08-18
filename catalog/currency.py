"""Centralized decimal currency conversion and formatting.

- Product prices are stored canonically in SAR.
- Displayed YER equals SAR multiplied by the admin-editable `StoreSettings.sar_to_yer_rate`.
- Do not persist converted prices.
- Display whole YER values (no decimals).
- All arithmetic uses `Decimal`; avoid floating point.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.cache import cache


def _get_rate() -> Decimal:
    """Return the current SAR→YER rate from cached StoreSettings."""
    from catalog.models import StoreSettings

    rate = cache.get("sar_to_yer_rate")
    if rate is None:
        settings = StoreSettings.get_current()
        rate = settings.sar_to_yer_rate
        cache.set("sar_to_yer_rate", rate, timeout=3600)
    return rate


def invalidate_rate_cache():
    cache.delete("sar_to_yer_rate")


def sar_to_yer(price_sar: Decimal) -> Decimal:
    """Convert a SAR Decimal to YER Decimal using the current rate."""
    rate = _get_rate()
    return price_sar * rate


def sar_to_yer_display(price_sar: Decimal) -> int:
    """Return whole YER value (int) for display."""
    yer = sar_to_yer(price_sar)
    return int(yer.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_sar(price_sar: Decimal) -> str:
    """Format SAR price for display, e.g. '١٢٠٫٠٠ ر.س'."""
    return f"{price_sar:,.2f} ر.س"


def format_yer(price_sar: Decimal) -> str:
    """Format YER price for display, e.g. '٤٩٬٢٠٠ ر.ي'."""
    yer_value = sar_to_yer_display(price_sar)
    return f"{yer_value:,} ر.ي"
