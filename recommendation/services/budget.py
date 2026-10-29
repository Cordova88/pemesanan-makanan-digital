"""Deterministic money bounds; independent of provider and checkout pricing."""

from decimal import Decimal, InvalidOperation
from typing import Self, TypedDict


class BudgetPayload(TypedDict):
    minimum: str | None
    maximum: str | None
    minimum_inclusive: bool
    maximum_inclusive: bool


class BudgetConstraint:
    __slots__ = ("__minimum", "__maximum", "__minimum_inclusive", "__maximum_inclusive")

    def __init__(
        self,
        minimum: Decimal | None = None,
        maximum: Decimal | None = None,
        *,
        minimum_inclusive: bool = True,
        maximum_inclusive: bool = True,
    ) -> None:
        for value in (minimum, maximum):
            if value is not None and (not value.is_finite() or value < 0 or value > 1_000_000):
                raise ValueError("Batas harga harus antara Rp0 dan Rp1.000.000.")

        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("Batas minimum tidak boleh melebihi maksimum.")

        self.__minimum: Decimal | None = minimum
        self.__maximum: Decimal | None = maximum
        self.__minimum_inclusive: bool = minimum_inclusive
        self.__maximum_inclusive: bool = maximum_inclusive

    @property
    def minimum(self) -> Decimal | None:
        return self.__minimum

    @property
    def maximum(self) -> Decimal | None:
        return self.__maximum

    @property
    def minimum_inclusive(self) -> bool:
        return self.__minimum_inclusive

    @property
    def maximum_inclusive(self) -> bool:
        return self.__maximum_inclusive

    def allows(self, price: Decimal) -> bool:
        if self.minimum is not None and (
            price < self.minimum or (price == self.minimum and not self.minimum_inclusive)
        ):
            return False

        if self.maximum is not None and (
            price > self.maximum or (price == self.maximum and not self.maximum_inclusive)
        ):
            return False

        return True

    @property
    def legacy_maximum(self) -> int | None:
        if self.maximum is None or self.maximum != self.maximum.to_integral_value():
            return None

        return int(self.maximum)

    def to_dict(self) -> BudgetPayload:
        return {
            "minimum": str(self.minimum) if self.minimum is not None else None,
            "maximum": str(self.maximum) if self.maximum is not None else None,
            "minimum_inclusive": self.minimum_inclusive,
            "maximum_inclusive": self.maximum_inclusive,
        }

    @classmethod
    def from_dict(cls, data: BudgetPayload) -> Self:
        try:
            if set(data) != {"minimum", "maximum", "minimum_inclusive", "maximum_inclusive"}:
                raise ValueError("Invalid budget fields")

            if any(
                type(data[key]) is not bool for key in ("minimum_inclusive", "maximum_inclusive")
            ):
                raise ValueError("Invalid budget flags")

            if any(
                data[key] is not None and not isinstance(data[key], str)
                for key in ("minimum", "maximum")
            ):
                raise ValueError("Invalid budget amount")

            return cls(
                Decimal(data["minimum"]) if data["minimum"] is not None else None,
                Decimal(data["maximum"]) if data["maximum"] is not None else None,
                minimum_inclusive=data["minimum_inclusive"],
                maximum_inclusive=data["maximum_inclusive"],
            )
        except (InvalidOperation, TypeError, KeyError) as error:
            raise ValueError("Invalid budget state") from error

    def __eq__(self, other: object) -> bool:
        return isinstance(other, BudgetConstraint) and (
            self.minimum,
            self.maximum,
            self.minimum_inclusive,
            self.maximum_inclusive,
        ) == (other.minimum, other.maximum, other.minimum_inclusive, other.maximum_inclusive)

    def __hash__(self) -> int:
        return hash((self.minimum, self.maximum, self.minimum_inclusive, self.maximum_inclusive))

    @staticmethod
    def rupiah(value: Decimal) -> str:
        return "Rp" + f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

    def description(self) -> str:
        parts: list[str] = []

        if self.minimum is not None:
            parts.append(
                ("minimal " if self.minimum_inclusive else "lebih dari ")
                + self.rupiah(self.minimum)
            )

        if self.maximum is not None:
            parts.append(
                ("maksimal " if self.maximum_inclusive else "kurang dari ")
                + self.rupiah(self.maximum)
            )

        return " dan ".join(parts)
