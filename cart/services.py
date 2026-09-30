"""Session-backed cart. It deliberately stores IDs only; menu prices remain server-side."""
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError

from menu.models import AddOn, MenuItem, VariantOption


class CartService:
    SESSION_KEY = "cart"

    def __init__(self, session):
        self.session = session
        self._lines = session.get(self.SESSION_KEY, [])

    @staticmethod
    def _ids(values, field_name):
        if not isinstance(values, list) or any(not isinstance(value, int) for value in values):
            raise ValidationError({field_name: "Must be a list of integer IDs."})
        return sorted(set(values))

    def _save(self):
        self.session[self.SESSION_KEY] = self._lines
        self.session.modified = True

    def add_item(self, menu_item_id, quantity, variant_ids=None, addon_ids=None):
        if not isinstance(menu_item_id, int):
            raise ValidationError({"menu_item_id": "Must be an integer."})
        if not isinstance(quantity, int) or quantity < 1:
            raise ValidationError({"quantity": "Must be a positive integer."})
        variants = self._ids(variant_ids or [], "variant_ids")
        addons = self._ids(addon_ids or [], "addon_ids")
        # Same configuration can be combined. Different selection sets always remain separate lines.
        for line in self._lines:
            if line["menu_item_id"] == menu_item_id and line["variant_ids"] == variants and line["addon_ids"] == addons:
                line["quantity"] += quantity
                self._save()
                return line
        line = {"id": uuid4().hex, "menu_item_id": menu_item_id, "quantity": quantity, "variant_ids": variants, "addon_ids": addons}
        self._lines.append(line)
        self._save()
        return line

    def remove_item(self, line_id):
        remaining = [line for line in self._lines if line["id"] != line_id]
        if len(remaining) == len(self._lines):
            raise ValidationError("Cart line not found.")
        self._lines = remaining
        self._save()

    def update_quantity(self, line_id, quantity):
        if not isinstance(quantity, int):
            raise ValidationError({"quantity": "Must be an integer."})
        if quantity <= 0:
            return self.remove_item(line_id)
        for line in self._lines:
            if line["id"] == line_id:
                line["quantity"] = quantity
                self._save()
                return line
        raise ValidationError("Cart line not found.")

    def clear(self):
        self._lines = []
        self._save()

    def checkout_items(self):
        """Return a copy in the exact input shape expected by OrderService."""
        return [{key: line[key] for key in ("menu_item_id", "quantity", "variant_ids", "addon_ids")} for line in self._lines]

    def get_items(self):
        """Resolve current data for display. Never use a stored browser/session price."""
        rendered = []
        for line in self._lines:
            try:
                item = MenuItem.objects.select_related("category").get(pk=line["menu_item_id"])
            except MenuItem.DoesNotExist:
                rendered.append({**line, "valid": False, "error": "Menu item no longer exists."})
                continue
            options = list(VariantOption.objects.select_related("group").filter(pk__in=line["variant_ids"]))
            addons = list(AddOn.objects.filter(pk__in=line["addon_ids"]))
            valid = (item.is_active and item.is_available and item.category.is_active and len(options) == len(line["variant_ids"]) and len(addons) == len(line["addon_ids"]))
            unit_price = item.price + sum((option.price_adjustment for option in options), Decimal("0")) + sum((addon.price for addon in addons), Decimal("0"))
            rendered.append({**line, "name": item.name, "valid": valid, "unit_price": format(unit_price, ".2f"), "line_total": format(unit_price * line["quantity"], ".2f"), "variants": [{"id": option.id, "name": option.name} for option in options], "addons": [{"id": addon.id, "name": addon.name} for addon in addons]})
        return rendered

    def get_total(self):
        return sum((Decimal(line["line_total"]) for line in self.get_items() if line.get("valid")), Decimal("0.00"))
