from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from .models import MenuItem
@require_GET
def customer_menu(request):
    items = MenuItem.objects.filter(is_active=True, is_available=True, category__is_active=True).select_related("category").prefetch_related("variant_groups__options", "allowed_addons")
    return JsonResponse({"items": [{
        "id": item.id, "name": item.name, "description": item.description, "price": format(item.price, ".2f"), "category": item.category.name,
        "variants": [{"id": group.id, "name": group.name, "required": group.is_required, "options": [{"id": option.id, "name": option.name, "price_adjustment": format(option.price_adjustment, ".2f")} for option in group.options.filter(is_active=True)]} for group in item.variant_groups.filter(is_active=True)],
        "addons": [{"id": addon.id, "name": addon.name, "price": format(addon.price, ".2f")} for addon in item.allowed_addons.filter(is_active=True, is_available=True)],
    } for item in items]})


def storefront(request):
    """Customer-facing shell; live menu and cart data are loaded from server APIs."""
    return render(request, "menu/storefront.html")
