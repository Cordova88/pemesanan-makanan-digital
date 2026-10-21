"""Existing order creation inputs, shared with session cart checkout."""

from typing import NotRequired, TypedDict


class OrderItemInput(TypedDict):
    menu_item_id: int
    quantity: int | str
    variant_ids: NotRequired[list[int]]
    addon_ids: NotRequired[list[int]]


class OrderInput(TypedDict, total=False):
    customer_name: str
    phone: str
    order_type: str
    table_token: str
    note: str
    items: list[OrderItemInput]
