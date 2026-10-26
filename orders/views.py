from decimal import Decimal
from django.http import HttpRequest, HttpResponse
import json
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from cart.services import CartService
from .models import Order, Table
from .permissions import cashier_required
from .services import (
    cancel,
    cashier_add_item,
    change_table,
    create_order,
    edit_item,
    expire_order_if_due,
    pay,
    process_qr_payment,
    refund,
    update_customer,
)


def _body(request: HttpRequest) -> dict[str, object]:
    return json.loads(request.body or "{}")


def _money(value: Decimal) -> str:
    return format(value, ".2f")


def _order(order: Order) -> dict[str, object]:
    payment_info = None
    try:
        if hasattr(order, "payment") and order.payment:
            payment_info = {
                "method": order.payment.method,
                "amount": _money(order.payment.amount),
                "paid_at": order.payment.paid_at.isoformat(),
                "external_reference": order.payment.external_reference,
            }
    except Exception:
        payment_info = None

    return {
        "public_id": order.public_id,
        "status": order.status,
        "is_paid": order.is_paid,
        "total": _money(order.total),
        "expires_at": order.expires_at.isoformat(),
        "qr_reference": order.public_id,
        "pay_qr_url": f"/orders/{order.public_id}/pay-qr/",
        "payment": payment_info,
        "note": order.note,
        "order_type": order.order_type,
        "table": (
            {"number": order.table.number, "token": order.table.token} if order.table_id else None
        ),
        "items": [
            {
                "id": x.id,
                "name": x.item_name,
                "menu_item_id": x.menu_item_id,
                "image_url": x.menu_item.image.url if x.menu_item and x.menu_item.image else "",
                "quantity": x.quantity,
                "unit_price": _money(x.unit_price),
                "line_total": _money(x.line_total),
                "variants": [{"name": v.option_name} for v in x.variants.all()],
                "addons": [{"name": a.addon_name} for a in x.addons.all()],
            }
            for x in order.items.select_related("menu_item").all()
        ],
    }


@require_POST
def checkout(request: HttpRequest) -> JsonResponse:
    try:
        payload = _body(request)
        cart = CartService(request.session)
        payload["items"] = cart.checkout_items()

        if not isinstance(payload.get("note", ""), str):
            raise ValidationError("Catatan harus berupa teks.")

        kitchen_notes = [
            f"{line['name']} × {line['quantity']}: {line['note']}"
            for line in cart.get_items()
            if line.get("note")
        ]
        payload["note"] = "\n".join(filter(None, [payload.get("note", "").strip(), *kitchen_notes]))
        order = create_order(payload)
        cart.clear()  # Only executed after the atomic order service has succeeded.

        return JsonResponse(_order(order), status=201)
    except (ValidationError, KeyError, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_GET
def lookup(request: HttpRequest, public_id: str) -> JsonResponse:
    try:
        return JsonResponse(_order(expire_order_if_due(public_id)))
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found."}, status=404)


@require_GET
def confirmation(request: HttpRequest, public_id: str) -> HttpResponse:
    """Public, refresh-safe confirmation shell; live order data is fetched from the API."""

    return render(request, "orders/confirmation.html", {"public_id": public_id})


@require_GET
def table_context(request: HttpRequest, token: str) -> JsonResponse:
    """Public QR resolver: lookup only; it never creates an order or session assignment."""

    try:
        table = Table.objects.get(token=token, is_active=True)

        return JsonResponse({"token": table.token, "number": table.number})
    except Table.DoesNotExist:
        return JsonResponse({"error": "The table QR code is invalid or inactive."}, status=404)


@login_required
@require_POST
def confirm_payment(request: HttpRequest, public_id: str) -> JsonResponse:
    try:
        cashier_required(request.user)
        body = _body(request)

        if not isinstance(body, dict):
            raise ValidationError("Payment request must be a JSON object.")

        order = pay(
            public_id,
            request.user,
            body.get("method", "CASH"),
            body.get("external_reference", ""),
            body.get("amount_received"),
        )

        return JsonResponse(_order(order))
    except (ValidationError, Order.DoesNotExist, ValueError, TypeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@login_required
@require_POST
def cancel_order(request: HttpRequest, public_id: str) -> JsonResponse:
    try:
        cashier_required(request.user)

        return JsonResponse(_order(cancel(public_id, request.user)))
    except (ValidationError, Order.DoesNotExist) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@login_required
@require_POST
def add_order_item(request: HttpRequest, public_id: str) -> JsonResponse:
    try:
        cashier_required(request.user)

        return JsonResponse(_order(cashier_add_item(public_id, _body(request), request.user)))
    except (ValidationError, Order.DoesNotExist, KeyError, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@login_required
@require_POST
def change_order_item(request: HttpRequest, public_id: str, line_id: int) -> JsonResponse:
    try:
        cashier_required(request.user)

        return JsonResponse(
            _order(edit_item(public_id, line_id, int(_body(request)["quantity"]), request.user))
        )
    except (ValidationError, Order.DoesNotExist, KeyError, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@login_required
@require_POST
def change_customer(request: HttpRequest, public_id: str) -> JsonResponse:
    try:
        cashier_required(request.user)

        return JsonResponse(_order(update_customer(public_id, _body(request), request.user)))
    except (ValidationError, Order.DoesNotExist) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@login_required
@require_POST
def change_order_table(request: HttpRequest, public_id: str) -> JsonResponse:
    try:
        cashier_required(request.user)

        return JsonResponse(
            _order(change_table(public_id, _body(request).get("table_token"), request.user))
        )
    except (ValidationError, Order.DoesNotExist) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@login_required
@require_POST
def refund_order(request: HttpRequest, public_id: str) -> JsonResponse:
    try:
        return JsonResponse(_order(refund(public_id, request.user)))
    except (ValidationError, Order.DoesNotExist) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@csrf_exempt
def qr_payment(request: HttpRequest, public_id: str) -> HttpResponse:
    """
    Fake online payment gateway:
    When the QR code is scanned (or simulated via GET/POST),
    it automatically completes the transaction for the exact required amount.
    """
    wants_json = (
        request.headers.get("Accept") == "application/json"
        or request.content_type == "application/json"
        or request.GET.get("format") == "json"
        or request.method == "POST"
    )

    try:
        order = process_qr_payment(public_id)

        if wants_json:
            return JsonResponse({
                "success": True,
                "message": "Pembayaran berhasil diselesaikan.",
                "order": _order(order),
            })

        return render(
            request,
            "orders/payment_success.html",
            {
                "order": order,
                "public_id": public_id,
                "total_formatted": _money(order.total),
                "paid_at": order.paid_at,
                "reference": (
                    order.payment.external_reference
                    if hasattr(order, "payment") and order.payment
                    else ""
                ),
            },
        )
    except Order.DoesNotExist:
        if wants_json:
            return JsonResponse({"error": "Order not found."}, status=404)
        return render(
            request,
            "orders/payment_error.html",
            {"error": "Pesanan tidak ditemukan.", "public_id": public_id},
            status=404,
        )
    except ValidationError as exc:
        msg = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        if wants_json:
            return JsonResponse({"error": msg}, status=400)
        return render(
            request,
            "orders/payment_error.html",
            {"error": msg, "public_id": public_id},
            status=400,
        )

