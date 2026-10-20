"""Typing schemas for existing session/API dictionaries; no runtime conversion."""

from typing import NotRequired, TypedDict


class CartLine(TypedDict):
    id: str
    menu_item_id: int
    quantity: int
    variant_ids: list[int]
    addon_ids: list[int]
    note: NotRequired[str]


class CartUpdatePayload(TypedDict, total=False):
    quantity: int
    variant_ids: list[int]
    addon_ids: list[int]
    note: str


class RenderedCartLine(CartLine, total=False):
    name: str
    image_url: str
    category: str
    valid: bool
    error: str
    unit_price: str
    line_total: str
    variants: list[dict[str, object]]
    addons: list[dict[str, object]]
