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
        self, minimum: Decimal | None = None, maximum: Decimal | None = None,
        *, minimum_inclusive: bool = True, maximum_inclusive: bool = True,
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
        if self.minimum is not None and (price < self.minimum or (price == self.minimum and not self.minimum_inclusive)):
            return False
        if self.maximum is not None and (price > self.maximum or (price == self.maximum and not self.maximum_inclusive)):
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
            if any(type(data[key]) is not bool for key in ("minimum_inclusive", "maximum_inclusive")):
                raise ValueError("Invalid budget flags")
            if any(data[key] is not None and not isinstance(data[key], str) for key in ("minimum", "maximum")):
                raise ValueError("Invalid budget amount")
            return cls(
                Decimal(data["minimum"]) if data["minimum"] is not None else None,
                Decimal(data["maximum"]) if data["maximum"] is not None else None,
                minimum_inclusive=data["minimum_inclusive"], maximum_inclusive=data["maximum_inclusive"],
            )
        except (InvalidOperation, TypeError, KeyError) as error:
            raise ValueError("Invalid budget state") from error

    def __eq__(self, other: object) -> bool:
        return isinstance(other, BudgetConstraint) and (
            self.minimum, self.maximum, self.minimum_inclusive, self.maximum_inclusive,
        ) == (other.minimum, other.maximum, other.minimum_inclusive, other.maximum_inclusive)

    def __hash__(self) -> int:
        return hash((self.minimum, self.maximum, self.minimum_inclusive, self.maximum_inclusive))

    def intersect(self, other: "BudgetConstraint") -> "BudgetConstraint":
        minimum = self.minimum
        min_inclusive = self.minimum_inclusive
        if other.minimum is not None and (minimum is None or other.minimum > minimum):
            minimum, min_inclusive = other.minimum, other.minimum_inclusive
        elif other.minimum is not None and other.minimum == minimum:
            min_inclusive = min_inclusive and other.minimum_inclusive
        maximum = self.maximum
        max_inclusive = self.maximum_inclusive
        if other.maximum is not None and (maximum is None or other.maximum < maximum):
            maximum, max_inclusive = other.maximum, other.maximum_inclusive
        elif other.maximum is not None and other.maximum == maximum:
            max_inclusive = max_inclusive and other.maximum_inclusive
        return BudgetConstraint(minimum, maximum, minimum_inclusive=min_inclusive, maximum_inclusive=max_inclusive)

    @staticmethod
    def rupiah(value: Decimal) -> str:
        return "Rp" + f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

    def description(self) -> str:
        parts: list[str] = []
        if self.minimum is not None:
            parts.append(("minimal " if self.minimum_inclusive else "lebih dari ") + self.rupiah(self.minimum))
        if self.maximum is not None:
            parts.append(("maksimal " if self.maximum_inclusive else "kurang dari ") + self.rupiah(self.maximum))
        return " dan ".join(parts)


class NumericMention:
    """Ephemeral role of a number in normalized input; never persisted as history."""

    __slots__ = ('value', 'role', 'start', 'end')

    def __init__(self, value: Decimal, role: str, start: int, end: int) -> None:
        if role not in {'MONEY', 'PERSON_COUNT', 'QUANTITY', 'TIME', 'TABLE_NUMBER',
                        'REFERENCE', 'MEASUREMENT', 'RATING', 'PERSONAL_FINANCE', 'OTHER'}:
            raise ValueError('Invalid numeric role')
        self.value: Decimal = value
        self.role: str = role
        self.start: int = start
        self.end: int = end


class BudgetRequest:
    def __init__(
        self, kind: str = "none", constraint: BudgetConstraint | None = None,
        *, correction: bool = False, clarification: str | None = None,
        scope: str = 'CURRENT_SEARCH', amount: Decimal | None = None,
        person_count: int | None = None, requested_categories: tuple[str, ...] = (),
        soft_target: Decimal | None = None, scope_ambiguous: bool = False,
    ) -> None:
        self.kind: str = kind
        self.constraint: BudgetConstraint | None = constraint
        self.correction: bool = correction
        self.clarification: str | None = clarification
        if scope not in {'CURRENT_SEARCH', 'PLAN_TOTAL', 'GROUP_TOTAL', 'PER_PERSON'}:
            raise ValueError('Invalid budget scope')
        self.scope: str = scope
        self.amount: Decimal | None = amount
        self.person_count: int | None = person_count
        self.requested_categories: tuple[str, ...] = requested_categories
        if soft_target is not None:
            BudgetConstraint(maximum=soft_target)
        self.soft_target: Decimal | None = soft_target
        self.scope_ambiguous: bool = scope_ambiguous
        self.numeric_roles: tuple[NumericMention, ...] = ()
