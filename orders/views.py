import json
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from cart.services import CartService
from .models import Order, Table
from .permissions import cashier_required
from .services import cancel, cashier_add_item, change_table, create_order, edit_item, expire_order_if_due, pay, refund, update_customer
def _body(request): return json.loads(request.body or "{}")
def _money(value): return format(value, ".2f")
def _order(order): return {"public_id":order.public_id,"status":order.status,"total":_money(order.total),"expires_at":order.expires_at.isoformat(),"qr_reference":order.public_id,"order_type":order.order_type,"table":({"number":order.table.number,"token":order.table.token} if order.table_id else None),"items":[{"id":x.id,"name":x.item_name,"quantity":x.quantity,"unit_price":_money(x.unit_price),"line_total":_money(x.line_total)} for x in order.items.all()]}
@require_POST
def checkout(request):
    try:
        payload = _body(request)
        cart = CartService(request.session)
        payload["items"] = cart.checkout_items()
        order = create_order(payload)
        cart.clear()  # Only executed after the atomic order service has succeeded.
        return JsonResponse(_order(order),status=201)
    except (ValidationError,KeyError,ValueError) as exc: return JsonResponse({"error":str(exc)},status=400)
@require_GET
def lookup(request,public_id):
    try: return JsonResponse(_order(expire_order_if_due(public_id)))
    except Order.DoesNotExist: return JsonResponse({"error":"Order not found."},status=404)

@require_GET
def confirmation(request, public_id):
    """Public, refresh-safe confirmation shell; live order data is fetched from the API."""
    return render(request, "orders/confirmation.html", {"public_id": public_id})

@require_GET
def table_context(request, token):
    """Public QR resolver: lookup only; it never creates an order or session assignment."""
    try:
        table = Table.objects.get(token=token, is_active=True)
        return JsonResponse({"token": table.token, "number": table.number})
    except Table.DoesNotExist:
        return JsonResponse({"error": "The table QR code is invalid or inactive."}, status=404)
@login_required
@require_POST
def confirm_payment(request,public_id):
    try: cashier_required(request.user); body=_body(request); return JsonResponse(_order(pay(public_id,request.user,body.get("method","CASH"),body.get("external_reference",""))))
    except (ValidationError,Order.DoesNotExist) as exc: return JsonResponse({"error":str(exc)},status=400)
@login_required
@require_POST
def cancel_order(request,public_id):
    try: cashier_required(request.user); return JsonResponse(_order(cancel(public_id,request.user)))
    except (ValidationError,Order.DoesNotExist) as exc: return JsonResponse({"error":str(exc)},status=400)
@login_required
@require_POST
def add_order_item(request,public_id):
    try: cashier_required(request.user); return JsonResponse(_order(cashier_add_item(public_id,_body(request),request.user)))
    except (ValidationError,Order.DoesNotExist,KeyError,ValueError) as exc: return JsonResponse({"error":str(exc)},status=400)
@login_required
@require_POST
def change_order_item(request,public_id,line_id):
    try: cashier_required(request.user); return JsonResponse(_order(edit_item(public_id,line_id,int(_body(request)["quantity"]),request.user)))
    except (ValidationError,Order.DoesNotExist,KeyError,ValueError) as exc: return JsonResponse({"error":str(exc)},status=400)
@login_required
@require_POST
def change_customer(request,public_id):
    try: cashier_required(request.user); return JsonResponse(_order(update_customer(public_id,_body(request),request.user)))
    except (ValidationError,Order.DoesNotExist) as exc: return JsonResponse({"error":str(exc)},status=400)
@login_required
@require_POST
def change_order_table(request, public_id):
    try:
        cashier_required(request.user)
        return JsonResponse(_order(change_table(public_id, _body(request).get("table_token"), request.user)))
    except (ValidationError, Order.DoesNotExist) as exc: return JsonResponse({"error":str(exc)},status=400)
@login_required
@require_POST
def refund_order(request,public_id):
    try: return JsonResponse(_order(refund(public_id,request.user)))
    except (ValidationError,Order.DoesNotExist) as exc: return JsonResponse({"error":str(exc)},status=400)
