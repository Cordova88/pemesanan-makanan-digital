from django.http import HttpRequest
import json

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .services import CartService


def _body(request: HttpRequest) -> dict[str, object]:
    return json.loads(request.body or "{}")


def _response(cart: CartService) -> JsonResponse:
    items = cart.get_items()
    return JsonResponse({"items": items, "total": format(cart.get_total(), ".2f")})


@require_GET
def detail(request: HttpRequest) -> JsonResponse:
    return _response(CartService(request.session))


@require_POST
def add(request: HttpRequest) -> JsonResponse:
    try:
        payload = _body(request)
        cart = CartService(request.session)
        cart.add_item(payload.get("menu_item_id"), payload.get("quantity"), payload.get("variant_ids", []), payload.get("addon_ids", []), payload.get("note", ""))
        return _response(cart)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["PATCH", "DELETE"])
def line(request: HttpRequest, line_id: str) -> JsonResponse:
    try:
        cart = CartService(request.session)
        if request.method == "PATCH":
            payload = _body(request)
            if "variant_ids" in payload or "addon_ids" in payload or "note" in payload:
                cart.update_selection(line_id, payload)
            else:
                cart.update_quantity(line_id, payload.get("quantity"))
        else:
            cart.remove_item(line_id)
        return _response(cart)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["DELETE"])
def clear(request: HttpRequest) -> JsonResponse:
    cart = CartService(request.session)
    cart.clear()
    return _response(cart)
