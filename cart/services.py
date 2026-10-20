"""Session-backed cart. It deliberately stores IDs only; menu prices remain server-side."""

from typing import ClassVar
from django.contrib.sessions.backends.base import SessionBase
from orders.payloads import OrderItemInput
from .payloads import CartLine, CartUpdatePayload, RenderedCartLine
from decimal import Decimal
from copy import deepcopy
from uuid import uuid4

from django.core.exceptions import ValidationError

from menu.models import AddOn, MenuItem, VariantOption
from menu.selection import MenuSelection


class CartService:
    SESSION_KEY: ClassVar[str] = "cart"

    def __init__(self, session: SessionBase) -> None:
        self.session: SessionBase = session
        self._lines: list[CartLine] = deepcopy(session.get(self.SESSION_KEY, []))

    @staticmethod
    def _ids(values: object, field_name: str) -> list[int]:
        if not isinstance(values, list) or any(not isinstance(value, int) for value in values):
            raise ValidationError({field_name: "Must be a list of integer IDs."})

        return sorted(set(values))

    def _save(self) -> None:
        self.session[self.SESSION_KEY] = deepcopy(self._lines)
        self.session.modified = True

    def add_item(
        self,
        menu_item_id: int,
        quantity: int,
        variant_ids: list[int] | None = None,
        addon_ids: list[int] | None = None,
        note: str = '',
    ) -> CartLine:
        if not isinstance(note, str) or len(note) > 500:
            raise ValidationError({"note": "Catatan maksimal 500 karakter."})

        note = note.strip()

        if not isinstance(menu_item_id, int):
            raise ValidationError({"menu_item_id": "Must be an integer."})

        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            raise ValidationError({"quantity": "Must be a positive integer."})

        variants = self._ids(variant_ids or [], "variant_ids")
        addons = self._ids(addon_ids or [], "addon_ids")
        self._validate_selection(menu_item_id, variants, addons)

        # Same configuration can be combined. Different selection sets always remain separate lines.
        for line in self._lines:
            if (
                line["menu_item_id"] == menu_item_id
                and line["variant_ids"] == variants
                and line["addon_ids"] == addons
                and line.get("note", "") == note
            ):
                line["quantity"] += quantity
                self._save()

                return deepcopy(line)

        line: CartLine = {
            "id": uuid4().hex,
            "menu_item_id": menu_item_id,
            "quantity": quantity,
            "variant_ids": variants,
            "addon_ids": addons,
            "note": note,
        }
        self._lines.append(line)
        self._save()

        return deepcopy(line)

    @staticmethod
    def _validate_selection(menu_item_id: int, variants: list[int], addons: list[int]) -> None:
        try:
            item = MenuItem.objects.select_related("category").get(
                pk=menu_item_id, is_active=True, is_available=True, category__is_active=True
            )
        except MenuItem.DoesNotExist:
            raise ValidationError("Menu tidak tersedia.")

        MenuSelection.from_ids(
            item,
            variants,
            addons,
            invalid_variant="Pilih satu opsi untuk setiap varian wajib.",
            incomplete_groups="Pilih satu opsi untuk setiap varian wajib.",
            invalid_addon="Tambahan tidak tersedia untuk menu ini.",
        )

    def update_selection(self, line_id: str, payload: CartUpdatePayload) -> None:
        existing = next((line for line in self._lines if line["id"] == line_id), None)

        if existing is None:
            raise ValidationError("Cart line not found.")

        quantity = payload.get("quantity")
        note = payload.get("note", "")

        if not isinstance(quantity, int) or isinstance(quantity, bool) or not 1 <= quantity <= 99:
            raise ValidationError("Jumlah porsi harus 1 sampai 99.")

        if not isinstance(note, str) or len(note) > 500:
            raise ValidationError("Catatan maksimal 500 karakter.")

        variants = self._ids(payload.get("variant_ids", []), "variant_ids")
        addons = self._ids(payload.get("addon_ids", []), "addon_ids")
        self._validate_selection(existing["menu_item_id"], variants, addons)
        existing.update(
            quantity=quantity, variant_ids=variants, addon_ids=addons, note=note.strip()
        )
        self._save()

    def remove_item(self, line_id: str) -> None:
        remaining = [line for line in self._lines if line["id"] != line_id]

        if len(remaining) == len(self._lines):
            raise ValidationError("Cart line not found.")

        self._lines = remaining
        self._save()

    def update_quantity(self, line_id: str, quantity: int) -> CartLine | None:
        if not isinstance(quantity, int):
            raise ValidationError({"quantity": "Must be an integer."})

        if quantity <= 0:
            return self.remove_item(line_id)

        for line in self._lines:
            if line["id"] == line_id:
                line["quantity"] = quantity
                self._save()

                return deepcopy(line)

        raise ValidationError("Cart line not found.")

    def clear(self) -> None:
        self._lines = []
        self._save()

    def checkout_items(self) -> list[OrderItemInput]:
        """Return a copy in the exact input shape expected by OrderService."""

        return deepcopy(
            [
                {
                    "menu_item_id": line["menu_item_id"],
                    "quantity": line["quantity"],
                    "variant_ids": line["variant_ids"],
                    "addon_ids": line["addon_ids"],
                }
                for line in self._lines
            ]
        )

    def get_items(self) -> list[RenderedCartLine]:
        """Resolve current data for display. Never use a stored browser/session price."""
        rendered: list[RenderedCartLine] = []

        for line in deepcopy(self._lines):
            try:
                item = MenuItem.objects.select_related("category").get(pk=line["menu_item_id"])
            except MenuItem.DoesNotExist:
                rendered.append(
                    {
                        **line,
                        "name": "Menu tidak tersedia",
                        "valid": False,
                        "error": "Menu item no longer exists.",
                        "unit_price": "0.00",
                        "line_total": "0.00",
                        "variants": [],
                        "addons": [],
                    }
                )
                continue

            options = list(
                VariantOption.objects.select_related("group").filter(pk__in=line["variant_ids"])
            )
            addons = list(AddOn.objects.filter(pk__in=line["addon_ids"]))
            valid = (
                item.is_active
                and item.is_available
                and item.category.is_active
                and len(options) == len(line["variant_ids"])
                and len(addons) == len(line["addon_ids"])
            )
            unit_price = (
                item.price
                + sum((option.price_adjustment for option in options), Decimal("0"))
                + sum((addon.price for addon in addons), Decimal("0"))
            )
            rendered.append(
                {
                    **line,
                    "name": item.name,
                    "image_url": item.image.url if item.image else "",
                    "category": item.category.name,
                    "valid": valid,
                    "unit_price": format(unit_price, ".2f"),
                    "line_total": format(unit_price * line["quantity"], ".2f"),
                    "variants": [{"id": option.id, "name": option.name} for option in options],
                    "addons": [{"id": addon.id, "name": addon.name} for addon in addons],
                }
            )

        return rendered

    def get_total(self) -> Decimal:
        return sum(
            (Decimal(line["line_total"]) for line in self.get_items() if line.get("valid")),
            Decimal("0.00"),
        )
