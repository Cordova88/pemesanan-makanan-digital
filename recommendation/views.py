import json

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from cart.services import CartService
from menu.models import MenuItem

from .services.chatbot import ChatbotService
from .services.language import TAG_LABELS


def _body(request):
    return json.loads(request.body or "{}")


def _item(match):
    item = match.item
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "price": format(item.price, ".2f"),
        "labels": list(match.labels),
        "match_reasons": list(match.match_reasons),
        "variants": [
            {
                "id": group.id,
                "name": group.name,
                "required": group.is_required,
                "options": [
                    {
                        "id": option.id,
                        "name": option.name,
                        "price_adjustment": format(option.price_adjustment, ".2f"),
                    }
                    for option in group.options.filter(is_active=True)
                ],
            }
            for group in item.variant_groups.filter(is_active=True)
        ],
        "addons": [
            {"id": addon.id, "name": addon.name, "price": format(addon.price, ".2f")}
            for addon in item.allowed_addons.filter(is_active=True, is_available=True)
        ],
    }


def _public_preferences(preferences):
    return {
        **preferences,
        "tags": [
            TAG_LABELS[tag]
            for tag in preferences.get("tags", [])
            if tag in TAG_LABELS
        ],
        "mood_tags": [
            TAG_LABELS[tag]
            for tag in preferences.get("mood_tags", [])
            if tag in TAG_LABELS
        ],
        "excluded_tags": [
            TAG_LABELS[tag]
            for tag in preferences.get("excluded_tags", [])
            if tag in TAG_LABELS
        ],
        "soft_excluded_tags": [
            TAG_LABELS[tag]
            for tag in preferences.get("soft_excluded_tags", [])
            if tag in TAG_LABELS
        ],
    }


@require_POST
def chat(request):
    try:
        body = _body(request)
        result=ChatbotService(request.session).reply(
            body.get("message", ""),
            body.get("action") == "more",
            body.get("action"),
        )
        result["recommendations"] = [
            _item(item) for item in result["recommendations"]
        ]
        result["preferences"] = _public_preferences(result["preferences"])
        return JsonResponse(result)
    except (ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Pesan tidak valid."}, status=400)


@require_POST
def add_to_cart(request):
    try:
        body = _body(request)
        item = MenuItem.objects.get(pk=body.get("menu_item_id"))
        CartService(request.session).add_item(
            item.id,
            int(body.get("quantity", 1)),
            body.get("variant_ids", []),
            body.get("addon_ids", []),
        )
        return JsonResponse({"message": "✅ Sudah masuk ke keranjang!"})
    except (
        MenuItem.DoesNotExist,
        ValidationError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_GET
def chatbot_page(request):
    return render(request, "recommendation/chatbot.html")
