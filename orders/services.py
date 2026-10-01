"""Transactional domain services. Views only parse requests and invoke these."""
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from datetime import timedelta
from django.utils import timezone
from menu.models import AddOn, MenuItem, VariantOption
from .models import AuditLog, Order, OrderItem, OrderItemAddOn, OrderItemVariant, Payment, Table

def _role(user): return "ADMIN" if user and user.is_staff else "CASHIER" if user else "CUSTOMER"
def _audit(order, action, actor=None, before=None, after=None, **metadata):
    AuditLog.objects.create(order=order, action=action, actor=actor, actor_role=_role(actor), before=before or {}, after=after or {}, metadata=metadata)
def _pending(order):
    if order.status != Order.Status.PENDING: raise ValidationError("Only pending orders can be changed.")
    if timezone.now() >= order.expires_at:
        order.status=Order.Status.EXPIRED; order.save(update_fields=["status", "updated_at"]); _audit(order, AuditLog.Action.EXPIRED)
        raise ValidationError("Order has expired.")
def recalculate(order):
    total=order.items.aggregate(value=Sum("line_total"))["value"] or Decimal("0.00")
    order.total=total; order.save(update_fields=["total", "updated_at"]); return total
def _menu_item(item_id):
    try: item=MenuItem.objects.select_related("category").get(pk=item_id)
    except MenuItem.DoesNotExist: raise ValidationError("Menu item does not exist.")
    if not item.is_active or not item.is_available or not item.category.is_active: raise ValidationError(f"{item.name} is not available.")
    return item
def resolve_table_token(token):
    if not isinstance(token, str) or not token:
        raise ValidationError({"table_token": "Scan the QR code attached to your table for dine-in ordering."})
    try: table = Table.objects.get(token=token, is_active=True)
    except Table.DoesNotExist: raise ValidationError({"table_token": "The table QR code is invalid or inactive."})
    return table
def add_item(order, item_id, quantity, variant_ids=(), addon_ids=(), actor=None):
    if quantity < 1: raise ValidationError("Quantity must be positive.")
    item=_menu_item(item_id); options=list(VariantOption.objects.select_related("group").filter(pk__in=variant_ids, is_active=True, group__menu_item=item, group__is_active=True))
    if len(options)!=len(set(variant_ids)): raise ValidationError("Invalid variant selection.")
    selected_groups={o.group_id for o in options}
    required=set(item.variant_groups.filter(is_active=True,is_required=True).values_list("id",flat=True))
    if required-selected_groups or len(selected_groups)!=len(options): raise ValidationError("Select exactly one option for every required variant group.")
    addons=list(AddOn.objects.filter(pk__in=addon_ids,is_active=True,is_available=True,menu_items=item))
    if len(addons)!=len(set(addon_ids)): raise ValidationError("Invalid add-on selection.")
    unit=item.price+sum((o.price_adjustment for o in options),Decimal())+sum((a.price for a in addons),Decimal())
    line=OrderItem.objects.create(order=order,menu_item=item,item_name=item.name,base_price=item.price,unit_price=unit,quantity=quantity,line_total=unit*quantity)
    OrderItemVariant.objects.bulk_create([OrderItemVariant(order_item=line,variant_option=o,group_name=o.group.name,option_name=o.name,price_adjustment=o.price_adjustment) for o in options])
    OrderItemAddOn.objects.bulk_create([OrderItemAddOn(order_item=line,addon=a,addon_name=a.name,unit_price=a.price) for a in addons])
    recalculate(order); _audit(order,AuditLog.Action.ITEM_ADDED,actor,after={"item":item.name,"quantity":quantity,"total":str(order.total)})
    return line
@transaction.atomic
def create_order(payload):
    order_type=payload.get("order_type", "")
    table = resolve_table_token(payload.get("table_token")) if order_type == Order.OrderType.DINE_IN else None
    order=Order(customer_name=payload.get("customer_name","").strip(),phone=payload.get("phone","").strip(),order_type=order_type,table=table,note=payload.get("note","").strip(),expires_at=timezone.now()+timedelta(hours=1))
    order.full_clean(); order.save()
    items=payload.get("items",[])
    if not items: raise ValidationError("Cart cannot be empty.")
    for entry in items: add_item(order,entry["menu_item_id"],int(entry["quantity"]),entry.get("variant_ids",[]),entry.get("addon_ids",[]))
    _audit(order,AuditLog.Action.CREATED,after={"total":str(order.total)})
    return order
@transaction.atomic
def edit_item(public_id, line_id, quantity, actor):
    order=Order.objects.select_for_update().get(public_id=public_id); _pending(order)
    line=order.items.select_for_update().get(pk=line_id)
    before={"quantity":line.quantity,"total":str(order.total)}
    if quantity <= 0: line.delete(); action=AuditLog.Action.ITEM_REMOVED
    else: line.quantity=quantity; line.save(); action=AuditLog.Action.QUANTITY_CHANGED
    recalculate(order); _audit(order,action,actor,before=before,after={"quantity":quantity,"total":str(order.total)}); return order
@transaction.atomic
def update_customer(public_id, payload, actor):
    order=Order.objects.select_for_update().get(public_id=public_id); _pending(order)
    before={field:getattr(order,field) for field in ("customer_name","phone","order_type","note")}
    before["table"] = order.table.number if order.table_id else None
    for field in ("customer_name", "phone", "order_type", "note"):
        if field in payload: setattr(order,field,str(payload[field]).strip())
    if order.order_type == Order.OrderType.TAKEAWAY:
        order.table = None
    elif "table_token" in payload:
        order.table = resolve_table_token(payload["table_token"])
    order.full_clean(); order.save()
    after={field:getattr(order,field) for field in ("customer_name","phone","order_type","note")}; after["table"] = order.table.number if order.table_id else None
    _audit(order,AuditLog.Action.CUSTOMER_CHANGED,actor,before=before,after=after)
    return order
@transaction.atomic
def change_table(public_id, table_token, actor):
    order=Order.objects.select_for_update().select_related("table").get(public_id=public_id); _pending(order)
    if order.order_type != Order.OrderType.DINE_IN: raise ValidationError("Takeaway orders cannot be assigned to a table.")
    previous = order.table.number if order.table_id else None
    table = resolve_table_token(table_token)
    order.table = table; order.full_clean(); order.save(update_fields=["table", "updated_at"])
    _audit(order,AuditLog.Action.MODIFIED,actor,before={"table":previous},after={"table":table.number},change="TABLE_CHANGED")
    return order
@transaction.atomic
def cashier_add_item(public_id, payload, actor):
    order=Order.objects.select_for_update().get(public_id=public_id); _pending(order)
    add_item(order,payload["menu_item_id"],int(payload["quantity"]),payload.get("variant_ids",[]),payload.get("addon_ids",[]),actor)
    return order
@transaction.atomic
def pay(public_id, cashier, method="CASH", external_reference=""):
    order=Order.objects.select_for_update().get(public_id=public_id); _pending(order); recalculate(order)
    order.status=Order.Status.PAID; order.paid_at=timezone.now(); order.processed_by_cashier=cashier; order.save(update_fields=["status","paid_at","processed_by_cashier","updated_at"])
    Payment.objects.create(order=order,cashier=cashier,amount=order.total,method=method,external_reference=external_reference)
    _audit(order,AuditLog.Action.PAID,cashier,after={"amount":str(order.total)}); return order
@transaction.atomic
def cancel(public_id, cashier):
    order=Order.objects.select_for_update().get(public_id=public_id); _pending(order); order.status=Order.Status.CANCELLED; order.cancelled_at=timezone.now(); order.cancelled_by_cashier=cashier; order.save(update_fields=["status","cancelled_at","cancelled_by_cashier","updated_at"]); _audit(order,AuditLog.Action.CANCELLED,cashier); return order
@transaction.atomic
def refund(public_id, admin):
    if not admin.is_staff: raise PermissionDenied("Only administrators may refund.")
    order=Order.objects.select_for_update().get(public_id=public_id)
    if order.status != Order.Status.PAID: raise ValidationError("Only paid orders may be refunded.")
    order.status=Order.Status.REFUNDED; order.refunded_at=timezone.now(); order.refunded_by=admin; order.save(update_fields=["status","refunded_at","refunded_by","updated_at"]); _audit(order,AuditLog.Action.REFUNDED,admin); return order
def expire_pending_orders():
    with transaction.atomic():
        orders=Order.objects.select_for_update().filter(status=Order.Status.PENDING,expires_at__lte=timezone.now())
        for order in orders: order.status=Order.Status.EXPIRED; order.save(update_fields=["status","updated_at"]); _audit(order,AuditLog.Action.EXPIRED)

@transaction.atomic
def expire_order_if_due(public_id):
    """Materialize expiry for an individual public lookup without waiting for the scheduler."""
    order = Order.objects.select_for_update().get(public_id=public_id)
    if order.status == Order.Status.PENDING and order.expires_at <= timezone.now():
        order.status = Order.Status.EXPIRED
        order.save(update_fields=["status", "updated_at"])
        _audit(order, AuditLog.Action.EXPIRED)
    return order
