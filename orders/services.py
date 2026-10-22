"""Transactional domain services. Views only parse requests and invoke these."""

from collections.abc import Collection, Mapping
from django.contrib.auth.models import AbstractUser
from .payloads import OrderInput, OrderItemInput
from decimal import Decimal, InvalidOperation
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from datetime import timedelta
from django.utils import timezone
from menu.models import MenuItem
from menu.selection import MenuSelection
from .models import AuditLog, Order, OrderItem, OrderItemAddOn, OrderItemVariant, Payment, Table


def _role(user: AbstractUser | None) -> str:
    return "ADMIN" if user and user.is_staff else "CASHIER" if user else "CUSTOMER"


def _audit(
    order: Order,
    action: str,
    actor: AbstractUser | None = None,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
    **metadata: object,
) -> None:
    AuditLog.objects.create(
        order=order,
        action=action,
        actor=actor,
        actor_role=_role(actor),
        before=before or {},
        after=after or {},
        metadata=metadata,
    )


def _pending(order: Order) -> None:
    if not order.is_pending:
        raise ValidationError("Only pending orders can be changed.")

    if timezone.now() >= order.expires_at:
        order.status = Order.Status.EXPIRED
        order.save(update_fields=["status", "updated_at"])
        _audit(order, AuditLog.Action.EXPIRED)

        raise ValidationError("Order has expired.")


def recalculate(order: Order) -> Decimal:
    total = order.items.aggregate(value=Sum("line_total"))["value"] or Decimal("0.00")
    order.total = total
    order.save(update_fields=["total", "updated_at"])

    return total


def _menu_item(item_id: int) -> MenuItem:
    try:
        item = MenuItem.objects.select_related("category").get(pk=item_id)
    except MenuItem.DoesNotExist:
        raise ValidationError("Menu item does not exist.")

    if not item.is_active or not item.is_available or not item.category.is_active:
        raise ValidationError(f"{item.name} is not available.")

    return item


def resolve_table_token(token: object) -> Table:
    if not isinstance(token, str) or not token:
        raise ValidationError(
            {"table_token": "Scan the QR code attached to your table for dine-in ordering."}
        )

    try:
        table = Table.objects.get(token=token, is_active=True)
    except Table.DoesNotExist:
        raise ValidationError({"table_token": "The table QR code is invalid or inactive."})

    return table


def add_item(
    order: Order,
    item_id: int,
    quantity: int,
    variant_ids: Collection[int] = (),
    addon_ids: Collection[int] = (),
    actor: AbstractUser | None = None,
) -> OrderItem:
    return _add_item(order, item_id, quantity, variant_ids, addon_ids, actor)


def _add_item(
    order: Order,
    item_id: int,
    quantity: int,
    variant_ids: Collection[int] = (),
    addon_ids: Collection[int] = (),
    actor: AbstractUser | None = None,
    *,
    defer_total: bool = False,
) -> OrderItem:
    if quantity < 1:
        raise ValidationError("Quantity must be positive.")

    item = _menu_item(item_id)
    selection = MenuSelection.from_ids(item, variant_ids, addon_ids)
    options, addons = selection.options, selection.addons
    unit = selection.unit_price
    line = OrderItem.objects.create(
        order=order,
        menu_item=item,
        item_name=item.name,
        base_price=item.price,
        unit_price=unit,
        quantity=quantity,
        line_total=unit * quantity,
    )
    OrderItemVariant.objects.bulk_create(
        [
            OrderItemVariant(
                order_item=line,
                variant_option=o,
                group_name=o.group.name,
                option_name=o.name,
                price_adjustment=o.price_adjustment,
            )
            for o in options
        ]
    )
    OrderItemAddOn.objects.bulk_create(
        [
            OrderItemAddOn(order_item=line, addon=a, addon_name=a.name, unit_price=a.price)
            for a in addons
        ]
    )
    if defer_total:
        # Only create_order uses this for a new order inside its atomic transaction.
        # Keep the running total for ITEM_ADDED audit records; persist it once below.
        order.total += line.line_total
    else:
        recalculate(order)
    _audit(
        order,
        AuditLog.Action.ITEM_ADDED,
        actor,
        after={"item": item.name, "quantity": quantity, "total": str(order.total)},
    )

    return line


@transaction.atomic
def create_order(payload: OrderInput) -> Order:
    order_type = payload.get("order_type", "")
    table = (
        resolve_table_token(payload.get("table_token"))
        if order_type == Order.OrderType.DINE_IN
        else None
    )
    order = Order(
        customer_name=payload.get("customer_name", "").strip(),
        phone=payload.get("phone", "").strip(),
        order_type=order_type,
        table=table,
        note=payload.get("note", "").strip(),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    order.full_clean()
    order.save()
    items = payload.get("items", [])

    if not items:
        raise ValidationError("Cart cannot be empty.")

    for entry in items:
        _add_item(
            order,
            entry["menu_item_id"],
            int(entry["quantity"]),
            entry.get("variant_ids", []),
            entry.get("addon_ids", []),
            defer_total=True,
        )

    recalculate(order)
    _audit(order, AuditLog.Action.CREATED, after={"total": str(order.total)})

    return order


@transaction.atomic
def edit_item(public_id: str, line_id: int, quantity: int, actor: AbstractUser) -> Order:
    order = Order.objects.select_for_update().get(public_id=public_id)
    _pending(order)
    line = order.items.select_for_update().get(pk=line_id)
    before = {"quantity": line.quantity, "total": str(order.total)}

    if quantity <= 0:
        line.delete()
        action = AuditLog.Action.ITEM_REMOVED
    else:
        line.quantity = quantity
        line.save()
        action = AuditLog.Action.QUANTITY_CHANGED

    recalculate(order)
    _audit(
        order, action, actor, before=before, after={"quantity": quantity, "total": str(order.total)}
    )

    return order


@transaction.atomic
def update_customer(public_id: str, payload: Mapping[str, object], actor: AbstractUser) -> Order:
    order = Order.objects.select_for_update().get(public_id=public_id)
    _pending(order)
    before = {
        field: getattr(order, field) for field in ("customer_name", "phone", "order_type", "note")
    }
    before["table"] = order.table.number if order.table_id else None

    for field in ("customer_name", "phone", "order_type", "note"):
        if field in payload:
            setattr(order, field, str(payload[field]).strip())

    if order.order_type == Order.OrderType.TAKEAWAY:
        order.table = None
    elif "table_token" in payload:
        order.table = resolve_table_token(payload["table_token"])

    order.full_clean()
    order.save()
    after = {
        field: getattr(order, field) for field in ("customer_name", "phone", "order_type", "note")
    }
    after["table"] = order.table.number if order.table_id else None
    _audit(order, AuditLog.Action.CUSTOMER_CHANGED, actor, before=before, after=after)

    return order


@transaction.atomic
def change_table(public_id: str, table_token: object, actor: AbstractUser) -> Order:
    order = Order.objects.select_for_update().select_related("table").get(public_id=public_id)
    _pending(order)

    if order.order_type != Order.OrderType.DINE_IN:
        raise ValidationError("Takeaway orders cannot be assigned to a table.")

    previous = order.table.number if order.table_id else None
    table = resolve_table_token(table_token)
    order.table = table
    order.full_clean()
    order.save(update_fields=["table", "updated_at"])
    _audit(
        order,
        AuditLog.Action.MODIFIED,
        actor,
        before={"table": previous},
        after={"table": table.number},
        change="TABLE_CHANGED",
    )

    return order


@transaction.atomic
def cashier_add_item(public_id: str, payload: OrderItemInput, actor: AbstractUser) -> Order:
    order = Order.objects.select_for_update().get(public_id=public_id)
    _pending(order)
    add_item(
        order,
        payload["menu_item_id"],
        int(payload["quantity"]),
        payload.get("variant_ids", []),
        payload.get("addon_ids", []),
        actor,
    )

    return order


def _cash_amount(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValidationError({"amount_received": "Enter the cash amount received."})

    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValidationError({"amount_received": "Enter a valid cash amount."}) from exc

    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
        raise ValidationError({"amount_received": "Enter a valid cash amount."})

    if amount > Decimal("9999999999.99"):
        raise ValidationError({"amount_received": "Cash amount is too large."})

    return amount


@transaction.atomic
def pay(
    public_id: str,
    cashier: AbstractUser,
    method: str = 'CASH',
    external_reference: object = '',
    amount_received: object = None,
) -> Order:
    order = Order.objects.select_for_update().get(public_id=public_id)
    _pending(order)

    if method not in Payment.Method.values:
        raise ValidationError({"method": "Unsupported payment method."})

    if not isinstance(external_reference, str) or len(external_reference) > 128:
        raise ValidationError({"external_reference": "Invalid payment reference."})

    if not order.items.exists():
        raise ValidationError("An empty order cannot be paid.")

    amount_due = recalculate(order)
    cash_received = None
    change_given = None

    if method == Payment.Method.CASH:
        cash_received = _cash_amount(amount_received)

        if cash_received < amount_due:
            raise ValidationError({"amount_received": "Cash received is less than the amount due."})

        change_given = cash_received - amount_due

    order.status = Order.Status.PAID
    order.paid_at = timezone.now()
    order.processed_by_cashier = cashier
    order.save(update_fields=["status", "paid_at", "processed_by_cashier", "updated_at"])
    Payment.objects.create(
        order=order,
        cashier=cashier,
        amount=amount_due,
        amount_received=cash_received,
        change_given=change_given,
        method=method,
        external_reference=external_reference,
    )
    audit_after = {"amount": format(amount_due, ".2f")}

    if method == Payment.Method.CASH:
        audit_after.update(
            amount_received=format(cash_received, ".2f"),
            change_given=format(change_given, ".2f"),
        )

    _audit(order, AuditLog.Action.PAID, cashier, after=audit_after)

    return order


@transaction.atomic
def cancel(public_id: str, cashier: AbstractUser) -> Order:
    order = Order.objects.select_for_update().get(public_id=public_id)
    _pending(order)
    order.status = Order.Status.CANCELLED
    order.cancelled_at = timezone.now()
    order.cancelled_by_cashier = cashier
    order.save(update_fields=["status", "cancelled_at", "cancelled_by_cashier", "updated_at"])
    _audit(order, AuditLog.Action.CANCELLED, cashier)

    return order


@transaction.atomic
def refund(public_id: str, admin: AbstractUser) -> Order:
    if not admin.is_staff:
        raise PermissionDenied("Only administrators may refund.")

    order = Order.objects.select_for_update().get(public_id=public_id)

    if not order.is_paid:
        raise ValidationError("Only paid orders may be refunded.")

    order.status = Order.Status.REFUNDED
    order.refunded_at = timezone.now()
    order.refunded_by = admin
    order.save(update_fields=["status", "refunded_at", "refunded_by", "updated_at"])
    _audit(order, AuditLog.Action.REFUNDED, admin)

    return order


def expire_pending_orders() -> None:
    with transaction.atomic():
        orders = Order.objects.select_for_update().filter(
            status=Order.Status.PENDING, expires_at__lte=timezone.now()
        )

        for order in orders:
            order.status = Order.Status.EXPIRED
            order.save(update_fields=["status", "updated_at"])
            _audit(order, AuditLog.Action.EXPIRED)


@transaction.atomic
def expire_order_if_due(public_id: str) -> Order:
    """Materialize expiry for an individual public lookup without waiting for the scheduler."""
    order = Order.objects.select_for_update().get(public_id=public_id)

    if order.status == Order.Status.PENDING and order.expires_at <= timezone.now():
        order.status = Order.Status.EXPIRED
        order.save(update_fields=["status", "updated_at"])
        _audit(order, AuditLog.Action.EXPIRED)

    return order
