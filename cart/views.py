import json

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .services import CartService


def _body(request):
    return json.loads(request.body or "{}")


def _response(cart):
    items = cart.get_items()
    return JsonResponse({"items": items, "total": format(cart.get_total(), ".2f")})


@require_GET
def detail(request):
    return _response(CartService(request.session))


@require_POST
def add(request):
    try:
        payload = _body(request)
        cart = CartService(request.session)
        cart.add_item(payload.get("menu_item_id"), payload.get("quantity"), payload.get("variant_ids", []), payload.get("addon_ids", []))
        return _response(cart)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["PATCH", "DELETE"])
def line(request, line_id):
    try:
        cart = CartService(request.session)
        if request.method == "PATCH":
            cart.update_quantity(line_id, _body(request).get("quantity"))
        else:
            cart.remove_item(line_id)
        return _response(cart)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_http_methods(["DELETE"])
def clear(request):
    cart = CartService(request.session)
    cart.clear()
    return _response(cart)
