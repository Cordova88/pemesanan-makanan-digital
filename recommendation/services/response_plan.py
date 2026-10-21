"""Verified expression input, separate from interpretation and transactions."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from decimal import Decimal
from typing import ClassVar, TypedDict

from menu.selection import MenuSelection

from .language import tag_label
from .recommendation import RecommendationMatch, SearchConstraints
from .tag_extractor import Preferences


class ResponseFact(TypedDict):
    id: int
    name: str
    price: str
    base_price: str
    minimum_payable: str | None
    price_basis: str
    final_price_confirmed: bool
    quantity: int
    category: str
    catalog_tags: list[str]
    match_reasons: list[str]
    requested_tags: list[str]
    available: bool


class ResponsePlan:
    PURPOSES: ClassVar[frozenset[str]] = frozenset(
        {
            'recommendation',
            'catalog_question',
            'correction',
            'removal',
            'greeting',
            'selection',
            'switching',
            'budget',
            'nonfood',
            'clarification',
            'empty',
            'error',
            'help',
        }
    )
    TONES: ClassVar[frozenset[str]] = frozenset(
        {'friendly', 'concise', 'empathetic', 'neutral', 'clarifying'}
    )

    def __init__(
        self,
        purpose: str,
        matches: Sequence[RecommendationMatch],
        preferences: Preferences,
        *,
        intent: str | None = None,
        tone: str = 'friendly',
        constraints: SearchConstraints | None = None,
        required_clarification: str | None = None,
        quick_replies: Sequence[dict[str, str]] = (),
        quantities: Mapping[int, int] | None = None,
        verified_plan_minimum: Decimal | None = None,
    ) -> None:
        if purpose not in self.PURPOSES:
            raise ValueError('Unsupported response purpose')

        if tone not in self.TONES:
            raise ValueError('Unsupported response tone')

        quantities = dict(quantities or {})

        if any(
            type(identifier) is not int
            or identifier <= 0
            or type(quantity) is not int
            or not 1 <= quantity <= 99
            for identifier, quantity in quantities.items()
        ):
            raise ValueError('Invalid projected quantity')

        if verified_plan_minimum is not None and (
            not isinstance(verified_plan_minimum, Decimal)
            or not verified_plan_minimum.is_finite()
            or verified_plan_minimum < 0
        ):
            raise ValueError('Invalid verified plan minimum')

        self.__plan_minimum = (
            format(verified_plan_minimum, '.2f') if verified_plan_minimum is not None else None
        )
        self.__purpose: str = purpose
        self.__intent: str | None = intent
        self.__tone: str = tone
        self.__constraints: dict[str, object] = (
            deepcopy(constraints.to_dict()) if constraints is not None else {}
        )
        self.__clarification: str | None = required_clarification
        self.__quick_replies: list[dict[str, str]] = deepcopy(list(quick_replies))
        self.__affordable: bool = preferences.prefer_affordable
        self.__preferences: tuple[str, ...] = tuple(
            sorted(tag_label(tag) for tag in preferences.tags | preferences.mood_tags)
        )
        facts = []
        self.__quote_signatures: dict[int, tuple | None] = {}

        for match in matches:
            quote = MenuSelection.minimum_quote(match.item)
            self.__quote_signatures[match.item.pk] = quote.signature if quote is not None else None
            facts.append(
                ResponseFact(
                    id=match.item.pk,
                    name=match.item.name,
                    price=format(match.item.price, '.2f'),
                    category=match.item.category.name,
                    base_price=format(
                        quote.base_price if quote is not None else match.item.price, '.2f'
                    ),
                    minimum_payable=(
                        format(quote.minimum_payable, '.2f') if quote is not None else None
                    ),
                    price_basis='minimum_payable',
                    final_price_confirmed=False,
                    quantity=quantities.get(match.item.pk, 1),
                    catalog_tags=sorted(tag.name for tag in match.item.tags.all()),
                    match_reasons=[
                        reason
                        for reason in match.match_reasons
                        if not reason.casefold().startswith('✅ tanpa')
                    ],
                    requested_tags=sorted(preferences.tags | preferences.mood_tags),
                    available=quote is not None,
                )
            )

        self.__items: tuple[ResponseFact, ...] = tuple(facts)

    @property
    def purpose(self) -> str:
        return self.__purpose

    @property
    def allowed_menu_names(self) -> tuple[str, ...]:
        return tuple(item['name'] for item in self.__items)

    @property
    def selected_menu_ids(self) -> tuple[int, ...]:
        return tuple(item['id'] for item in self.__items)

    @property
    def tone(self) -> str:
        return self.__tone

    @property
    def required_clarification(self) -> str | None:
        return self.__clarification

    @property
    def allowed_claims(self) -> tuple[str, ...]:
        return (
            'catalog_identity',
            'displayed_price',
            'catalog_category',
            'verified_tags',
            'active_filters',
        )

    @property
    def quick_replies(self) -> list[dict[str, str]]:
        return deepcopy(self.__quick_replies)

    @property
    def allowed_prices(self) -> tuple[str, ...]:
        return tuple(item['price'] for item in self.__items)

    @property
    def facts(self) -> list[ResponseFact]:
        return deepcopy(list(self.__items))

    @property
    def quote_signatures(self) -> dict[int, tuple | None]:
        """Local freshness evidence; excluded from provider-facing projections."""

        return dict(self.__quote_signatures)

    def wording_packet(self) -> dict[str, object]:
        """Public catalog facts only. Numbers/scopes/warnings stay with backend."""
        items = []

        for fact in self.__items:
            labels = {tag_label(tag) for tag in fact['catalog_tags']}
            items.append(
                {
                    'id': fact['id'],
                    'name': fact['name'],
                    'category': fact['category'],
                    'catalog_tags': list(fact['catalog_tags']),
                    'match_reasons': [
                        reason for reason in fact['match_reasons'] if reason in labels
                    ],
                }
            )

        return {
            'purpose': self.purpose,
            'tone': self.tone,
            'items': items,
            'selected_menu_ids': list(self.selected_menu_ids),
            'allowed_claims': ['catalog_identity', 'verified_tags'],
        }

    def to_dict(self) -> dict[str, object]:
        return {
            'intent': self.__intent,
            'purpose': self.purpose,
            'tone': self.tone,
            'preferences': list(self.__preferences),
            'items': self.facts,
            'selected_menu_ids': list(self.selected_menu_ids),
            'allowed_claims': list(self.allowed_claims),
            'constraints': deepcopy(self.__constraints),
            'required_clarification': self.required_clarification,
            'prefer_affordable': self.__affordable,
            'verified_plan_minimum': self.__plan_minimum,
            'quick_replies': self.quick_replies,
        }
