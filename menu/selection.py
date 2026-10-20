"""Validated menu selections shared by session carts and transactional orders."""

from collections.abc import Collection, Iterable
from decimal import Decimal
from typing import Self

from django.core.exceptions import ValidationError

from .models import AddOn, MenuItem, VariantOption


class MinimumQuote:
    """Request-local lower bound and provenance, never a final customer choice."""

    def __init__(self, base_price: Decimal, minimum_payable: Decimal, signature: tuple) -> None:
        self.__base_price = base_price
        self.__minimum_payable = minimum_payable
        self.__signature = signature

    @property
    def base_price(self) -> Decimal:
        return self.__base_price

    @property
    def minimum_payable(self) -> Decimal:
        return self.__minimum_payable

    @property
    def signature(self) -> tuple:
        return self.__signature


class MenuSelection:
    def __init__(
        self,
        item: MenuItem,
        options: Iterable[VariantOption] = (),
        addons: Iterable[AddOn] = (),
    ) -> None:
        self.item: MenuItem = item
        self.__options: tuple[VariantOption, ...] = tuple(options)
        self.__addons: tuple[AddOn, ...] = tuple(addons)

    @classmethod
    def from_ids(
        cls,
        item: MenuItem,
        variant_ids: Collection[int] = (),
        addon_ids: Collection[int] = (),
        *,
        invalid_variant: str = "Invalid variant selection.",
        incomplete_groups: str = "Select exactly one option for every required variant group.",
        invalid_addon: str = "Invalid add-on selection.",
    ) -> Self:
        """Resolve current catalog data while retaining caller-specific errors."""
        options = list(
            VariantOption.objects.select_related("group").filter(
                pk__in=variant_ids,
                is_active=True,
                group__menu_item=item,
                group__is_active=True,
            )
        )

        if len(options) != len(set(variant_ids)):
            raise ValidationError(invalid_variant)

        groups = {option.group_id for option in options}
        required = set(
            item.variant_groups.filter(
                is_active=True,
                is_required=True,
            ).values_list("id", flat=True)
        )

        if required - groups or len(groups) != len(options):
            raise ValidationError(incomplete_groups)

        addons = list(
            AddOn.objects.filter(
                pk__in=addon_ids,
                is_active=True,
                is_available=True,
                menu_items=item,
            )
        )

        if len(addons) != len(set(addon_ids)):
            raise ValidationError(invalid_addon)

        return cls(item, options, addons)

    @property
    def options(self) -> tuple[VariantOption, ...]:
        return self.__options

    @property
    def addons(self) -> tuple[AddOn, ...]:
        return self.__addons

    @property
    def unit_price(self) -> Decimal:
        return (
            self.item.price
            + sum((option.price_adjustment for option in self.__options), Decimal())
            + sum((addon.price for addon in self.__addons), Decimal())
        )

    @classmethod
    def minimum_payable(cls, item: MenuItem) -> Decimal | None:
        """Quote the cheapest complete required selection, without optional extras.

        This is a lower bound, not the customer's final selection. Resolve through
        the same validator and price property used by carts and orders.
        """

        if not item.is_active or not item.is_available or not item.category.is_active:
            return None

        identifiers = []

        for group in item.variant_groups.filter(is_active=True, is_required=True):
            option = group.options.filter(is_active=True).order_by('price_adjustment', 'pk').first()

            if option is None:
                return None

            identifiers.append(option.pk)

        try:
            return cls.from_ids(item, identifiers).unit_price
        except ValidationError:
            return None

    @staticmethod
    def _quote_signature(item: MenuItem) -> tuple:
        groups = []

        for group in item.variant_groups.order_by('pk').prefetch_related('options'):
            options = (
                tuple(
                    sorted(
                        (option.pk, option.is_active, str(option.price_adjustment))
                        for option in group.options.all()
                    )
                )
                if group.is_active and group.is_required
                else ()
            )
            groups.append((group.pk, group.is_active, group.is_required, options))

        return (
            item.pk,
            str(item.price),
            item.is_active,
            item.is_available,
            item.category_id,
            item.category.is_active,
            tuple(groups),
        )

    @classmethod
    def minimum_quote(cls, item: MenuItem) -> MinimumQuote | None:
        """Bind the existing price calculation to freshly read required options.

        Fail closed if provenance changes during capture. Optional addons/options
        remain outside this lower bound; cart/order selection stays authoritative.
        """
        current = MenuItem.objects.select_related('category').filter(pk=item.pk).first()

        if current is None:
            return None

        signature = cls._quote_signature(current)
        amount = cls.minimum_payable(current)
        after = MenuItem.objects.select_related('category').filter(pk=item.pk).first()

        if (
            amount is None
            or not amount.is_finite()
            or amount < 0
            or after is None
            or signature != cls._quote_signature(after)
        ):
            return None

        return MinimumQuote(current.price, amount, signature)

    def total_price(self, quantity: int) -> Decimal:
        if type(quantity) is not int or not 1 <= quantity <= 99:
            raise ValidationError('Quantity must be an integer between 1 and 99.')

        return self.unit_price * quantity
