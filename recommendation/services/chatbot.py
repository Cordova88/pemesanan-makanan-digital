from collections.abc import Collection, Sequence
from .response_types import ChatbotResponse, QuickReply
from django.conf import settings
from django.contrib.sessions.backends.base import SessionBase
from typing import ClassVar
from decimal import Decimal
import re
from copy import deepcopy
from menu.models import AddOn, Category, MenuItem, MenuItemAlias, MenuTag, VariantOption
from menu.selection import MenuSelection
from .combination_planner import CombinationCandidate, CombinationPlanner
from .entity_resolver import EntityResolution, EntityResolver
from .decision_router import DecisionRouter, RoutingDecision

from .conversation_interpreter import (
    ConversationInterpretation,
    ConversationInterpreter,
    ConversationIntent,
    PreferenceOperation,
)
from .language import TAG_LABELS, normalize_text, tag_label
from .budget import BudgetConstraint, BudgetRequest
from .mood_extractor import MoodExtractor, UserContext
from .mood_resolver import MoodResolver
from .recommendation import RecommendationMatch, RecommendationService, SearchConstraints
from .tag_extractor import Preferences, PreferencesPayload, TagExtractor
from .ai.GeminiInterpreter import GeminiInterpreter
from .ai.explanations import RecommendationExplanationService
from .ai.semantic_reranker import SemanticReranker
from .gemini import GeminiClient
from .text_generator import TextGenerator
from .conversation_session import ConversationSession, ConversationStatePayload
from .response_composer import LocalResponseComposer
from .response_plan import ResponsePlan
from .telemetry import fallback_event, ranking_event
from .plan_interpreter import PlanDelta, PlanInterpreter


class ChatbotService:
    SESSION_KEY: ClassVar[str] = ConversationSession.STATE_KEY
    SHOWN_KEY: ClassVar[str] = ConversationSession.SHOWN_KEY
    SEARCH_KEY: ClassVar[str] = ConversationSession.SEARCH_KEY
    LAST_RESULT_EMPTY_KEY: ClassVar[str] = ConversationSession.LAST_RESULT_EMPTY_KEY
    RESET_PHRASES: ClassVar[set[str]] = {"reset", "mulai lagi", "mulai dari awal"}
    CONFUSION_PHRASES: ClassVar[set[str]] = {
        "bingung",
        "gatau",
        "ga tau",
        "gak tau",
        "tidak tahu",
        "terserah",
        "terserah deh",
        "nggak tau",
        "susah pilih",
        "mau makan apa",
    }
    MORE_PHRASES: ClassVar[set[str]] = {
        "cari yang lain",
        "cari menu lain",
        "menu lain",
        "yang lain",
        "lainnya",
        "rekomendasi lain",
    }
    OPEN_FOLLOWUP_ANSWERS: ClassVar[set[str]] = {
        "bebas",
        "bebas aja",
        "bebas saja",
        "bebas kok",
        "apa aja",
        "apa saja",
        "terserah",
        "terserah deh",
        "mana aja",
        "mana saja",
    }
    GEMINI_CALLS_KEY: ClassVar[str] = ConversationSession.GEMINI_CALLS_KEY
    TAG_DIMENSIONS: ClassVar[tuple[frozenset[str], ...]] = (
        frozenset({'rice', 'noodle', 'fried_rice', 'fried_noodle'}),
        frozenset(
            {'chicken', 'beef', 'duck', 'fish', 'seafood', 'shrimp', 'egg', 'tofu', 'tempeh'}
        ),
        frozenset({'hot', 'warm', 'cold'}),
    )
    FOOD_TAGS: ClassVar[frozenset[str]] = frozenset(
        {
            'rice',
            'noodle',
            'fried_rice',
            'fried_noodle',
            'chicken',
            'beef',
            'duck',
            'fish',
            'shrimp',
            'seafood',
            'egg',
            'tofu',
            'tempeh',
            'bread',
            'heavy_meal',
            'light_meal',
            'snack',
            'dessert',
        }
    )

    @classmethod
    def _dimension_removals(cls, tags: set[str]) -> set[str]:
        return set().union(
            *(dimension - tags for dimension in cls.TAG_DIMENSIONS if tags & dimension)
        )

    def __init__(
        self,
        session: SessionBase,
        *,
        gemini_client: TextGenerator | None = None,
    ) -> None:
        self.session: SessionBase = session
        self._session_state: ConversationSession = ConversationSession(session)
        self._responses: LocalResponseComposer = LocalResponseComposer(session)
        self.tag_extractor: TagExtractor = TagExtractor()
        catalog_tags = (
            MenuTag.objects.filter(
                menu_items__is_active=True,
                menu_items__category__is_active=True,
            )
            .values_list("name", "display_name")
            .distinct()
        )
        catalog_aliases = (
            MenuTag.objects.filter(
                aliases__is_active=True,
                menu_items__is_active=True,
                menu_items__category__is_active=True,
            )
            .values_list("name", "aliases__phrase")
            .distinct()
        )
        self.tag_extractor.configure_catalog_tags(catalog_tags, catalog_aliases)
        self.tag_extractor.configure_categories(
            Category.objects.filter(is_active=True).values_list('name', flat=True)
        )
        self.plan_interpreter = PlanInterpreter(
            self.tag_extractor.price_parser,
            Category.objects.filter(is_active=True).values_list('name', flat=True),
        )
        self._plan_delta = PlanDelta()
        self._requested_quantity: int | None = None
        self._plan_changed = False
        self._plan_update_only = False
        self._plan_error = False
        self._combination_pending, self._combination_limited = False, False
        self._entity_resolver: EntityResolver = EntityResolver(
            MenuItem.objects.values_list("id", "name"),
            [alias for aliases in TagExtractor.ALIASES.values() for alias in aliases]
            + [phrase for _, phrase in catalog_aliases]
            + [name for name, _ in catalog_tags]
            + [display for _, display in catalog_tags if display]
            + list(self.tag_extractor.category_terms())
            + ['makan', 'minum'],
            aliases=MenuItemAlias.objects.filter(
                is_active=True,
                menu_item__is_active=True,
                menu_item__category__is_active=True,
            ).values_list('menu_item_id', 'phrase'),
        )
        self.mood_extractor: MoodExtractor = MoodExtractor()
        self._current_context: UserContext | None = None
        self._current_entity_text: str | None = None
        self.mood_resolver: MoodResolver = MoodResolver()
        self.recommender: RecommendationService = RecommendationService()
        self.interpreter: ConversationInterpreter = ConversationInterpreter(self.tag_extractor)
        self.gemini_client: TextGenerator = (
            GeminiClient() if gemini_client is None else gemini_client
        )
        from .ai.turn_generator import TurnGenerator

        self._turn_generator = TurnGenerator(self.gemini_client)
        self.gemini_interpreter: GeminiInterpreter = GeminiInterpreter(
            self._turn_generator,
            allowed_tags=self.tag_extractor.get_allowed_tags(),
        )
        self.explanation_service: RecommendationExplanationService = (
            RecommendationExplanationService(self._turn_generator)
        )
        self.semantic_reranker: SemanticReranker = SemanticReranker(self._turn_generator)
        self._semantic_query: str | None = None
        self._semantic_tags: set[str] = set()
        self.response_plan: ResponsePlan | None = None
        self._response_purpose: str = 'clarification'
        self._response_intent: str | None = None
        self._response_tone: str = 'friendly'
        self._context_action: str = 'NEW_REQUEST'
        self._context_block: str | None = None
        self._planned_entries: list[dict[str, int]] | None = None

    def _subjective_response(
        self,
        message: str,
        preferences: Preferences,
        budget: BudgetRequest,
    ) -> ChatbotResponse:
        """Retain objective local deltas; subjective wishes are ranking evidence."""
        self._response_intent = ConversationIntent.RECOMMEND
        extracted = self.tag_extractor.extract(message)
        semantic_tags = extracted.tags & {
            'light',
            'filling',
            'rich',
            'comfort_food',
            'satisfying',
            'quick_meal',
        }
        objective_tags = extracted.tags - semantic_tags
        previous = self._search_constraints()
        bans = preferences.excluded_tags | set(previous.excluded_tags) | extracted.excluded_tags
        objective_tags.difference_update(bans)
        operations = []

        for action, tags in (
            ('REMOVE', extracted.excluded_tags),
            ('SOFT_REMOVE', extracted.soft_excluded_tags - bans),
            ('ADD', objective_tags),
        ):
            if tags:
                operations.append(PreferenceOperation(action, tuple(sorted(tags))))

        interpretation = ConversationInterpretation(
            ConversationIntent.RECOMMEND,
            operations=operations or [PreferenceOperation('KEEP')],
            tags=objective_tags,
            excluded_tags=extracted.excluded_tags,
            soft_excluded_tags=extracted.soft_excluded_tags - bans,
            category=extracted.category,
            contextual_revision=not bool(objective_tags or extracted.category),
            message_is_meaningful=True,
        )
        self._semantic_query, self._semantic_tags = message, semantic_tags - bans

        # A general suitability request releases item focus, not hard constraints.
        if budget.kind != 'none':
            return self._budget_response(budget, message, preferences, interpretation)

        self._session_state.set_focus(None)
        updated = self._apply_interpretation(preferences, interpretation)
        updated.excluded_tags.update(bans)
        updated.tags.difference_update(bans)
        constraints = self._constraints_for_interpretation(interpretation)

        return self._recommend(updated, message, constraints=constraints)

    def reset(self) -> None:
        self._session_state.reset()

    def _consume_gemini_call(self) -> bool:
        return self._turn_generator.reserve(
            lambda: self._session_state.consume_gemini_call(settings.GEMINI_MAX_CALLS_PER_SESSION)
        )

    def _interpret_semantic(
        self,
        message: str,
        local: ConversationInterpretation,
        preferences: Preferences,
    ) -> ConversationInterpretation | None:
        """Opt-in v3 proposal; both wire versions use the same local filters."""

        if not getattr(settings, 'CHATBOT_PROPOSAL_V3_ENABLED', False):
            # Compatibility payload excludes history, mood, private graph and money.
            return self.gemini_interpreter.interpret(
                message,
                context={
                    'tags': sorted(preferences.tags),
                    'excluded_tags': sorted(preferences.excluded_tags),
                    'soft_excluded_tags': sorted(preferences.soft_excluded_tags),
                    'context_action': local.context_action,
                    'constraint_scope': local.constraint_scope,
                },
            )

        from .semantic_proposal import SemanticEvidence

        # Previous-context restores have already been resolved locally. Never
        # manufacture a previousN capability from provider text or an ordinal.
        if local.context_action == 'REFER_TO_PREVIOUS':
            return None

        revision = self._turn_source_session.get(ConversationSession.REVISION_KEY, 0)
        categories = list(Category.objects.filter(is_active=True).values_list('name', flat=True))
        hard = preferences.excluded_tags | set(self._search_constraints().excluded_tags)

        try:
            evidence = SemanticEvidence(
                message,
                local,
                allowed_tags=self.tag_extractor.get_allowed_tags(),
                hard_exclusions=hard,
                category_names=categories,
                context_action=local.context_action,
                constraint_scope=local.constraint_scope,
                revision=revision,
            )
        except ValueError:
            return None

        raw = self.gemini_interpreter.propose_v3(evidence.provider_packet(message))
        # Fresh facts and source revision, rather than the pre-call draft snapshot.
        roles = dict(
            MenuItem.objects.filter(
                is_active=True, is_available=True, category__is_active=True
            ).values_list('pk', 'category__name')
        )
        proposal = DecisionRouter.validate_proposal_v3(
            raw,
            evidence,
            current_revision=self._turn_source_session.get(ConversationSession.REVISION_KEY, 0),
            available_menu_ids=set(roles),
            catalog_roles=roles,
            active_categories=list(
                Category.objects.filter(is_active=True).values_list('name', flat=True)
            ),
        )

        if proposal is None or proposal.clarification_key is not None:
            return None

        # Existing PlanInterpreter/BudgetRequest already own numeric deltas.
        # A semantic proposal cannot replace or independently apply those DTOs.
        return proposal.interpretation

    @staticmethod
    def _eligible_for_gemini(message: str, interpretation: ConversationInterpretation) -> bool:
        # Compatibility facade; the live pipeline supplies entity, budget and state too.
        return DecisionRouter.decide(message, interpretation).route == RoutingDecision.AI_ASSISTED

    def _routing_clarification(
        self, preferences: Preferences, reason: str, entity: EntityResolution | None = None
    ) -> ChatbotResponse:
        self._context_action = 'CLARIFY'
        messages = {
            'ambiguous_catalog': 'Ada beberapa menu yang mungkin kamu maksud. Sebutkan satu nama menu yang ingin dipilih.',
            'missing_reference': 'Aku belum menemukan menu yang kamu maksud di pilihan sebelumnya. Sebutkan nama menunya, ya.',
            'proposal_unavailable': 'Aku belum bisa memastikan pilihan untuk permintaan itu. Boleh jelaskan jenis menu, rasa, atau preferensi yang paling penting?',
        }

        if entity is not None:
            if reason == 'ambiguous_catalog':
                names = list(
                    MenuItem.objects.filter(
                        pk__in=entity.menu_ids,
                        is_active=True,
                        is_available=True,
                        category__is_active=True,
                    )
                    .order_by('name', 'pk')
                    .values_list('name', flat=True)[:8]
                )

                if names:
                    messages[reason] = (
                        f"Yang kamu maksud {', '.join(names)}? Sebutkan satu nama menu, ya."
                    )
            elif reason == 'proposal_unavailable':
                messages[reason] = (
                    f"Boleh jelaskan yang kamu maksud dengan {entity.requested_entity}? Sebutkan nama menu atau jenis makanan/minuman yang kamu cari."
                )

        state = self._session_state.load_state().get('state', 'COLLECTING_PREFERENCES')

        return {
            'message': messages.get(reason) or self._unknown_response(''),
            'state': state,
            'preferences': preferences.to_dict(state=state),
            'recommendations': [],
            'quick_replies': [],
            'active_search': self._search_constraints().to_dict(),
        }

    def _preferences(self) -> Preferences:
        preferences = self._session_state.load_preferences()

        if ConversationSession.CONTEXTS_KEY in self.session:
            preferences.excluded_tags.update(self._session_state.global_exclusions())
            preferences.tags.difference_update(preferences.excluded_tags)

        return preferences

    def _search_constraints(self) -> SearchConstraints:
        search = self._session_state.load_constraints()

        if ConversationSession.CONTEXTS_KEY not in self.session:
            return search

        exclusions = search.excluded_tags | self._session_state.global_exclusions()

        return SearchConstraints(
            search.required_tags - exclusions,
            frozenset(exclusions),
            search.category,
            search.max_price,
            search.moods,
            budget=search.budget,
            soft_target=search.soft_target,
        )

    def _constraints_for_interpretation(
        self,
        interpretation: ConversationInterpretation,
        old_follow_up: str | None = None,
    ) -> SearchConstraints:
        previous = self._search_constraints()
        has_previous = bool(
            previous.required_tags
            or previous.excluded_tags
            or previous.category
            or previous.max_price is not None
            or previous.budget is not None
            or previous.soft_target is not None
            or previous.moods
        )
        constraint_only_update = (
            not interpretation.tags
            and not interpretation.excluded_tags
            and not interpretation.category
            and (
                interpretation.max_price is not None
                or interpretation.clear_max_price
                or interpretation.prefer_affordable
                or interpretation.clear_prefer_affordable
            )
        )
        continuing = (
            old_follow_up in {"meal_type", "base"}
            or (constraint_only_update and has_previous)
            or (
                interpretation.contextual_revision
                and (previous.budget is not None or previous.max_price is not None)
            )
            or (interpretation.contextual_revision and has_previous)
            or (not interpretation.tags and not interpretation.category and has_previous)
        )
        explicit_clear = any(operation.action == "CLEAR" for operation in interpretation.operations)

        if interpretation.intent == ConversationIntent.REPLACE_PREFERENCES:
            continuing = continuing and not explicit_clear

        if interpretation.intent == ConversationIntent.RETRY_SEARCH:
            continuing = False

        if (
            interpretation.category
            and previous.category
            and interpretation.category.casefold() != previous.category.casefold()
        ):
            continuing = False

        # The coordinator has already selected the active scope; only its local
        # bounds survive here. Overall and safety live outside this projection.
        base = previous
        required_tags = set(base.required_tags) if continuing else set()
        current_tags = set(interpretation.tags)

        if old_follow_up == "meal_type":
            current_tags.difference_update({"heavy_meal", "filling"})

        if continuing:
            required_tags.difference_update(self._dimension_removals(current_tags))

        if continuing and interpretation.intent == ConversationIntent.REPLACE_PREFERENCES:
            for operation in interpretation.operations:
                if operation.action == "REPLACE":
                    required_tags.difference_update(operation.remove_tags)

        for operation in interpretation.operations:
            if operation.action in {"DROP", "REMOVE", "SOFT_REMOVE"}:
                required_tags.difference_update(operation.tags)
            elif operation.action == "CLEAR_TAGS":
                required_tags.clear()

        required_tags.update(current_tags)
        excluded_tags = set(base.excluded_tags)
        excluded_tags.update(interpretation.excluded_tags)

        for operation in interpretation.operations:
            if operation.action in {"ADD", "REPLACE", "RELAX"}:
                excluded_tags.difference_update(operation.tags)

            if operation.action == "REPLACE":
                excluded_tags.difference_update(operation.remove_tags)

            if operation.action == "CLEAR_TAGS":
                excluded_tags.clear()

        category = interpretation.category or base.category

        if interpretation.category is None and (
            (base.category == 'Minuman' and current_tags & self.FOOD_TAGS)
            or (base.category == 'Makanan' and 'drink' in current_tags)
        ):
            category = None
            required_tags = set(current_tags)

        if interpretation.clear_max_price:
            max_price = None
        elif interpretation.max_price is not None:
            max_price = interpretation.max_price
        elif interpretation.contextual_revision and continuing:
            max_price = base.max_price
        else:
            max_price = base.max_price

        price_bounds = None if interpretation.clear_max_price else base.budget
        excluded_tags.update(self._session_state.global_exclusions())
        required_tags.difference_update(excluded_tags)

        if (
            self._current_context is not None
            and not interpretation.clear_max_price
            and interpretation.max_price is None
        ):
            max_price = previous.max_price
            price_bounds = previous.budget

        moods = set(base.moods)

        if interpretation.clear_moods:
            moods.clear()

        if interpretation.moods:
            moods = set(interpretation.moods)

        return SearchConstraints(
            required_tags=frozenset(required_tags),
            excluded_tags=frozenset(excluded_tags),
            category=category,
            max_price=max_price,
            moods=frozenset(moods),
            budget=price_bounds,
            soft_target=None if interpretation.clear_max_price else base.soft_target,
        )

    def _save(
        self,
        preferences: Preferences,
        state: str,
        follow_up: str | None = None,
    ) -> None:
        self._session_state.save_preferences(preferences, state, follow_up)

    @staticmethod
    def _has_preferences(preferences: Preferences) -> bool:
        return bool(
            preferences.tags
            or preferences.mood_tags
            or preferences.excluded_tags
            or preferences.soft_excluded_tags
            or preferences.max_price is not None
            or preferences.category
            or preferences.prefer_affordable
        )

    def _has_active_search(self) -> bool:
        constraints = self._search_constraints()

        return bool(
            constraints.required_tags
            or constraints.excluded_tags
            or constraints.category
            or constraints.max_price is not None
            or constraints.budget is not None
            or constraints.moods
        )

    @staticmethod
    def _quick_reply(label: str, value: str, action: str | None = None) -> QuickReply:
        reply: QuickReply = {"label": label, "value": value}

        if action:
            reply["action"] = action

        return reply

    def _question(self, confused: bool = False) -> ChatbotResponse:
        self._response_purpose = 'clarification' if confused else 'greeting'

        if confused:
            message = "Tenang, nggak perlu mikir 😄 Aku bantu pilih. Kamu lagi lebih ke..."
            replies = [
                self._quick_reply("😋 Lapar banget", "Aku lapar banget"),
                self._quick_reply("😫 Lagi capek", "Aku lagi capek"),
                self._quick_reply("😔 Makanan yang bikin nyaman", "Butuh comfort food"),
                self._quick_reply("🔥 Pengen pedas", "Pengen yang pedas"),
                self._quick_reply("🥤 Pengen yang segar", "Lagi gerah, pengen yang segar"),
                self._quick_reply("💸 Lagi hemat", "Lagi hemat"),
            ]
        else:
            message = "Hai! Aku bisa bantu kamu memilih menu. Lagi ingin makan atau minum apa?"
            replies = [
                self._quick_reply("🍚 Makanan berat", "Makanan berat"),
                self._quick_reply("🍟 Camilan", "Camilan"),
                self._quick_reply("🥤 Minuman", "Minuman"),
                self._quick_reply("🌶️ Pedas", "Pengen yang pedas"),
                self._quick_reply("💸 Lagi hemat", "Lagi hemat"),
            ]

        replies = self._catalog_quick_replies(replies)
        self._session_state.set_last_question("menu_choice")

        return {
            "message": message,
            "state": "COLLECTING_PREFERENCES",
            "preferences": Preferences().to_dict(),
            "recommendations": [],
            "quick_replies": replies,
        }

    def _catalog_quick_replies(self, replies: list[QuickReply]) -> list[QuickReply]:
        existing_values = {reply["value"] for reply in replies}
        catalog_tags = (
            MenuTag.objects.filter(
                menu_items__is_active=True,
                menu_items__category__is_active=True,
            )
            .exclude(name__in={"spicy", "chicken", "drink"})
            .values_list("name", "display_name")
            .distinct()[:4]
        )

        for name, display_name in catalog_tags:
            label = tag_label(name)
            value = f"Pengen yang {display_name or name.replace('_', ' ')}"

            if value in existing_values:
                continue

            replies.append(self._quick_reply(label, value))

        return replies

    @staticmethod
    def _response_preferences(
        preferences: Preferences,
        state: str,
        follow_up: str | None = None,
    ) -> PreferencesPayload:
        response = preferences.to_dict(state=state, follow_up=follow_up)
        response["max_price"] = None
        response["category"] = None

        return response

    def _ask_meal_type(self, preferences: Preferences) -> ChatbotResponse:
        self._session_state.set_last_question("meal_type")
        self._save(preferences, "ASKING_FOLLOWUP", follow_up="meal_type")

        return {
            "message": "Wah, tim pedas nih 🌶️ Kamu lebih pengen makanan berat atau cuma mau ngemil?",
            "state": "ASKING_FOLLOWUP",
            "preferences": self._response_preferences(
                preferences,
                "ASKING_FOLLOWUP",
                follow_up="meal_type",
            ),
            "recommendations": [],
            "quick_replies": [
                self._quick_reply("🍚 Makanan berat", "Makanan berat"),
                self._quick_reply("🍟 Camilan", "Camilan"),
            ],
        }

    def _ask_base(self, preferences: Preferences) -> ChatbotResponse:
        self._session_state.set_last_question("base")
        self._save(preferences, "ASKING_FOLLOWUP", follow_up="base")

        return {
            "message": "Sip! Kamu lebih pengen nasi atau mie? Kalau bebas, bilang aja ya 😄",
            "state": "ASKING_FOLLOWUP",
            "preferences": self._response_preferences(
                preferences,
                "ASKING_FOLLOWUP",
                follow_up="base",
            ),
            "recommendations": [],
            "quick_replies": [
                self._quick_reply("🍚 Nasi", "Pengen nasi"),
                self._quick_reply("🍜 Mie", "Pengen mie"),
                self._quick_reply("🤷 Bebas", "Bebas aja"),
            ],
        }

    def _unknown_response(self, source_text: str) -> str:
        variants = (
            "Hehe, aku belum menangkap maksudnya 😄",
            "Aku belum yakin maksudmu apa.",
            "Boleh kasih sedikit petunjuk?",
            "Aku masih belum menangkap yang kamu mau.",
        )

        return (
            self._responses.choose('unknown', variants)
            + "\nCoba kasih tahu misalnya kamu mau yang pedas, ayam, nasi, atau yang murah."
        )

    def _greeting_response(self, preferences: Preferences) -> ChatbotResponse:
        self._response_purpose = 'greeting'
        state = self._session_state.load_state().get('state', 'COLLECTING_PREFERENCES')

        return {
            'message': self._responses.choose(
                'greeting',
                (
                    'Halo! Aku bantu pilih menu yang cocok buat kamu.',
                    'Hai! Lagi ingin makanan atau minuman seperti apa?',
                    'Selamat datang! Mau cari menu berdasarkan selera atau budget?',
                    'Halo, mau melihat pilihan makanan atau minuman? Aku bisa bantu.',
                ),
            ),
            'state': state,
            'preferences': self._response_preferences(preferences, state),
            'recommendations': [],
            'quick_replies': [
                self._quick_reply('🍚 Makanan berat', 'Makanan berat'),
                self._quick_reply('🍟 Camilan', 'Camilan'),
                self._quick_reply('🥤 Minuman', 'Minuman'),
            ],
        }

    def _recommend(
        self,
        preferences: Preferences,
        source_text: str,
        more: bool = False,
        exclude_ids: Collection[int] | None = None,
        response_kind: str = 'recommendation',
        required_tags: Collection[str] | None = None,
        constraints: SearchConstraints | None = None,
        *,
        cheapest: bool = False,
    ) -> ChatbotResponse:
        preferences.mood_tags = self.mood_resolver.resolve(
            preferences.moods, explicit_tags=preferences.tags
        )
        preferences.mood_tags.difference_update(
            preferences.excluded_tags | preferences.soft_excluded_tags
        )

        if constraints is None:
            if required_tags is not None:
                constraints = SearchConstraints(
                    required_tags=frozenset(required_tags),
                    category=preferences.category,
                    max_price=preferences.max_price,
                    moods=frozenset(preferences.moods),
                )
            else:
                constraints = self._search_constraints()

        self._session_state.save_search(constraints, update_required_tags=True)
        focused = self._session_state.get_focus()
        shown = self._session_state.get_shown_ids()

        if more:
            exclude_ids = list(exclude_ids or shown or [])
            shown = list(shown)
        else:
            exclude_ids = list(exclude_ids or [])
            shown = []

        exclude_ids = list(set(exclude_ids) | set(self._session_state.get_explicit_rejections()))
        ranking_preferences = Preferences.from_dict(preferences.to_dict())
        ranking_preferences.tags.update(self._semantic_tags)
        pool = self.recommender.rank(
            ranking_preferences,
            limit=ConversationSession.MAX_HISTORY,
            exclude_ids=self._session_state.get_explicit_rejections(),
            constraints=constraints,
            include_unscored=self._semantic_query is not None,
        )
        pool = self._eligible_for_plan(pool)
        self._session_state.set_candidates([match.item.pk for match in pool])

        if more:
            self._session_state.set_focus(None)
            matches = [
                match
                for match in pool
                if match.item.pk not in exclude_ids and match.item.pk != focused
            ]

            if not matches and focused is not None:
                # A focused item is not the entire search. Previously shown
                # alternatives can be revisited when there are no unseen ones.
                matches = [match for match in pool if match.item.pk != focused]
        elif focused is not None:
            matches = [match for match in pool if match.item.pk == focused]

            if not matches:
                self._session_state.set_focus(None)
                matches = list(pool)
        else:
            matches = list(pool)

        semantic_applied = False
        expression_mode = getattr(settings, 'CHATBOT_AI_RESPONSE_MODE', 'ranking')
        wording_only = (
            self._semantic_query is not None and not cheapest and expression_mode == 'wording'
        )

        if self._semantic_query is not None and not cheapest and expression_mode == 'ranking':
            matches, semantic_applied = self._semantic_order(
                matches, ranking_preferences, constraints
            )
            matches = self._eligible_for_plan(matches)

        if cheapest:
            matches = sorted(
                matches,
                key=lambda match: (self._minimum_payable(match.item), match.item.name.casefold()),
            )[:3]
        else:
            matches = matches[:3]

        purpose = response_kind if response_kind in ResponsePlan.PURPOSES else 'recommendation'
        self._response_purpose = purpose if matches else 'empty'
        plan = ResponsePlan(
            purpose, matches, preferences, intent=self._response_intent, constraints=constraints
        )
        generated_intro, generated_explanations = None, {}

        if (
            wording_only
            and matches
            and getattr(settings, 'CHATBOT_AI_WORDING_ENABLED', False)
            and self._current_context is None
            and self._consume_gemini_call()
        ):
            matches, generated_intro, generated_explanations, unchanged = self._wording_for_plan(
                plan,
                matches,
                ranking_preferences,
                constraints,
            )
            semantic_applied = semantic_applied and unchanged
            plan = ResponsePlan(
                purpose, matches, preferences, intent=self._response_intent, constraints=constraints
            )
            self._response_purpose = purpose if matches else 'empty'

        explanations = {
            match.item.id: self.explanation_service.fallback(match) for match in matches
        }
        explanations.update(generated_explanations)
        local_message = self._responses.compose(plan)

        if generated_intro is not None and self._responses.accept_generated(generated_intro):
            local_message = generated_intro + '\n' + local_message.split('\n', 1)[-1]
        elif wording_only and getattr(settings, 'CHATBOT_AI_WORDING_ENABLED', False):
            fallback_event('wording')

        # Phase 2: LOCAL requests never spend a provider call on wording.
        new_ids = [match.item.id for match in matches]
        self._session_state.record_recommendations(
            new_ids,
            shown_ids=shown + new_ids if more else new_ids,
        )
        self._save(preferences, "RECOMMENDING")

        return {
            "message": (
                local_message
                if matches or not more
                else (
                    "Belum ada menu lain dalam batas budgetmu. Mau mencoba jenis makanan atau minuman lain?"
                    if constraints.budget is not None or constraints.max_price is not None
                    else "Belum ada menu lain yang sesuai. Mau mencoba jenis makanan atau minuman lain?"
                )
            )
            + (
                '\nUrutannya aku sesuaikan dengan seleramu. Kecocokannya tetap bersifat subjektif.'
                if self._semantic_query and matches and semantic_applied
                else (
                    '\nAku pilihkan dari menu yang tersedia. Mana yang paling cocok untuk seleramu belum bisa kupastikan.'
                    if self._semantic_query and len(matches) > 1
                    else ''
                )
            ),
            "state": "RECOMMENDING",
            "preferences": self._response_preferences(
                preferences,
                "RECOMMENDING",
            ),
            "active_search": constraints.to_dict(),
            "recommendations": matches,
            "explanations": explanations,
            "quick_replies": [
                self._quick_reply("🔄 Cari Menu Lain", "Cari menu lain", action="more"),
                self._quick_reply("🔄 Mulai Lagi", "mulai lagi", action="reset"),
            ],
        }

    def _wording_for_plan(
        self,
        plan: ResponsePlan,
        matches: list[RecommendationMatch],
        preferences: Preferences,
        constraints: SearchConstraints,
    ) -> tuple[list[RecommendationMatch], str | None, dict[int, str], bool]:
        # Never dispatch an expression task with a stale/ineligible fact packet.
        preflight = self._eligible_for_plan(
            self.recommender.rank(
                preferences,
                limit=ConversationSession.MAX_HISTORY,
                constraints=constraints,
                exclude_ids=self._session_state.get_explicit_rejections(),
                include_unscored=True,
            )
        )
        before = {match.item.pk: match for match in preflight}
        current = ResponsePlan(
            plan.purpose,
            [before[m.item.pk] for m in matches if m.item.pk in before],
            preferences,
            constraints=constraints,
        )

        if current.facts != plan.facts or current.quote_signatures != plan.quote_signatures:
            self._session_state.set_candidates([match.item.pk for match in preflight])

            return (
                [match for match in preflight if match.item.pk in plan.selected_menu_ids],
                None,
                {},
                False,
            )

        intro, explanations = self.explanation_service.from_plan(plan, matches, preferences)
        fresh_pool = self.recommender.rank(
            preferences,
            limit=ConversationSession.MAX_HISTORY,
            constraints=constraints,
            exclude_ids=self._session_state.get_explicit_rejections(),
            include_unscored=True,
        )
        fresh_pool = self._eligible_for_plan(fresh_pool)
        self._session_state.set_candidates([match.item.pk for match in fresh_pool])
        fresh_by_id = {match.item.pk: match for match in fresh_pool}
        fresh = [fresh_by_id[match.item.pk] for match in matches if match.item.pk in fresh_by_id]
        current = ResponsePlan(plan.purpose, fresh, preferences, constraints=constraints)

        if current.facts != plan.facts or current.quote_signatures != plan.quote_signatures:
            ids = set(plan.selected_menu_ids)

            return [match for match in fresh_pool if match.item.pk in ids], None, {}, False

        return fresh, intro, explanations, True

    def _semantic_order(
        self,
        matches: list[RecommendationMatch],
        preferences: Preferences,
        constraints: SearchConstraints,
    ) -> tuple[list[RecommendationMatch], bool]:
        reason = None

        if len(matches) < 2:
            reason = 'insufficient_candidates'
        elif not getattr(settings, 'CHATBOT_SEMANTIC_RERANKING_ENABLED', True):
            reason = 'feature_disabled'
        elif self._current_context is not None:
            reason = 'context_protected'
        elif not self._consume_gemini_call():
            reason = self._turn_generator.reservation_block_reason or 'session_limit_reached'

        if reason is not None:
            ranking_event(reason)
            fallback_event('ranking')

            return matches, False

        sent = matches[: SemanticReranker.MAX_CANDIDATES]
        snapshots = {match.item.pk: SemanticReranker.catalog_data(match) for match in sent}
        quotes = {match.item.pk: MenuSelection.minimum_quote(match.item) for match in sent}
        ready_pool = self._eligible_for_plan(
            self.recommender.rank(
                preferences,
                limit=ConversationSession.MAX_HISTORY,
                constraints=constraints,
                exclude_ids=self._session_state.get_explicit_rejections(),
                include_unscored=True,
            )
        )
        ready = {match.item.pk: match for match in ready_pool}
        ready_for_provider = all(
            quote is not None
            and identifier in ready
            and SemanticReranker.catalog_data(ready[identifier]) == snapshots[identifier]
            for identifier, quote in quotes.items()
        )

        # An unstable capture skips the provider but must still run the fresh
        # local filter below; returning the old matches would retain stale data.
        if not ready_for_provider:
            ranking_event('preflight_rejected')

        proposed = (
            self.semantic_reranker.rerank(matches, self._semantic_query or '')
            if ready_for_provider
            else None
        )
        # The catalog may change while the provider runs. Reuse the same local
        # filter/ranker, and never return stale prices or unavailable candidates.
        fresh_pool = self.recommender.rank(
            preferences,
            limit=ConversationSession.MAX_HISTORY,
            constraints=constraints,
            exclude_ids=self._session_state.get_explicit_rejections(),
            include_unscored=True,
        )
        self._session_state.set_candidates([match.item.pk for match in fresh_pool])
        original_ids = {match.item.pk for match in matches}
        fresh = [match for match in fresh_pool if match.item.pk in original_ids]
        by_id = {match.item.pk: match for match in fresh}
        fresh_quotes = {
            identifier: MenuSelection.minimum_quote(match.item)
            for identifier, match in by_id.items()
        }
        unchanged = all(
            identifier in by_id
            and SemanticReranker.catalog_data(by_id[identifier]) == snapshot
            and fresh_quotes[identifier] is not None
            and quotes[identifier] is not None
            and fresh_quotes[identifier].signature == quotes[identifier].signature
            for identifier, snapshot in snapshots.items()
        )

        if proposed is None or not unchanged:
            if not unchanged:
                ranking_event('catalog_changed')

            fallback_event('ranking')

            return fresh, False

        proposed_ids = [match.item.pk for match in proposed]

        if len(proposed_ids) != len(original_ids) or set(proposed_ids) != original_ids:
            ranking_event('candidate_mismatch')
            fallback_event('ranking')

            return fresh, False

        ranking_event('accepted')

        return [by_id[identifier] for identifier in proposed_ids if identifier in by_id], True

    def _answer_catalog_question(
        self,
        preferences: Preferences,
        interpretation: ConversationInterpretation,
        source_text: str,
        *,
        budget: BudgetConstraint | None = None,
    ) -> ChatbotResponse:
        self._response_purpose = 'catalog_question'
        tags = interpretation.catalog_tags
        previous = self._search_constraints()
        self._session_state.set_last_question(None)
        self._session_state.set_entity_ids([])
        target = previous.soft_target if budget is None else None
        budget = budget or previous.budget
        constraints = SearchConstraints(
            required_tags=frozenset(tags),
            excluded_tags=previous.excluded_tags
            | frozenset(preferences.excluded_tags)
            | frozenset(interpretation.excluded_tags),
            category=interpretation.category,
            max_price=(
                interpretation.max_price
                if interpretation.max_price is not None
                else previous.max_price
            ),
            budget=budget,
            soft_target=target,
        )
        self._session_state.save_search(constraints, update_required_tags=True)
        matches = self.recommender.find_catalog_matches(
            tags,
            excluded_tags=constraints.excluded_tags,
            category=interpretation.category,
            max_price=constraints.max_price,
            budget=budget,
            soft_target=constraints.soft_target,
        )
        self._session_state.set_candidates([match.item.pk for match in matches])
        state = self._session_state.load_state().get(
            "state",
            "COLLECTING_PREFERENCES",
        )

        if not matches:
            tag_labels = [tag_label(tag) for tag in sorted(tags)]
            requested = " dan ".join(tag_labels) or "pilihan itu"
            self._session_state.record_recommendations([])
            self._save(preferences, state)

            return {
                "message": (f"Aku belum menemukan menu {requested} yang tersedia saat ini."),
                "state": state,
                "preferences": self._response_preferences(
                    preferences,
                    state,
                ),
                "active_search": constraints.to_dict(),
                "recommendations": [],
                "catalog_question": True,
                "quick_replies": [],
            }

        explanations = {
            match.item.id: self.explanation_service.fallback(match) for match in matches
        }
        # Catalog facts and wording are produced locally for resolved queries.

        tag_labels = [tag_label(tag) for tag in sorted(tags)]
        requested = " dan ".join(tag_labels) or "pilihanmu"
        ids = [match.item.id for match in matches]
        self._session_state.record_recommendations(ids, shown_ids=list(ids))
        self._save(preferences, state)

        return {
            "message": self._responses.choose(
                'catalog',
                (
                    'Ini pilihan menu {requested} yang tersedia di katalog.',
                    'Berikut pilihan {requested} dari katalog saat ini.',
                    'Kartu berikut berisi pilihan menu {requested} yang ditemukan.',
                ),
            ).format(requested=requested),
            "state": state,
            "preferences": self._response_preferences(
                preferences,
                state,
            ),
            "active_search": constraints.to_dict(),
            "recommendations": matches,
            "catalog_question": True,
            "explanations": explanations,
            "quick_replies": [
                self._quick_reply("🔄 Mulai Lagi", "mulai lagi", action="reset"),
            ],
        }

    def _deterministic_variant(self, text: str, variants: Sequence[str]) -> str:
        return self._responses.choose('rejection', variants)

    def _apply_interpretation(
        self,
        preferences: Preferences,
        interpretation: ConversationInterpretation,
    ) -> Preferences:
        stored = self._session_state.load_state()
        current = Preferences.from_dict(stored) if stored else preferences

        if interpretation.intent == ConversationIntent.RESET:
            self.reset()

            return current

        if interpretation.intent in {
            ConversationIntent.GREETING,
            ConversationIntent.HELP,
            ConversationIntent.UNKNOWN,
            ConversationIntent.OUT_OF_SCOPE,
        }:
            return current

        hard_exclusions = set(current.excluded_tags)
        previous_category = self._search_constraints().category

        if previous_category == 'Minuman' and interpretation.tags & self.FOOD_TAGS:
            current.tags.discard('drink')

        if previous_category == 'Makanan' and 'drink' in interpretation.tags:
            current.tags.difference_update(self.FOOD_TAGS)

        if interpretation.tags:
            current.tags.difference_update(self._dimension_removals(interpretation.tags))

        current.apply_interpretation(interpretation, self.mood_resolver)

        if (interpretation.tags or interpretation.category) and stored.get('follow_up') not in {
            'meal_type',
            'base',
        }:
            # Display/persist the current positive scope, not a union of past
            # searches. Budget and hard exclusions remain separate constraints.
            current.tags = set(
                self._constraints_for_interpretation(
                    interpretation,
                    old_follow_up=stored.get('follow_up'),
                ).required_tags
            )

        if any(operation.action == 'CLEAR' for operation in interpretation.operations):
            current.excluded_tags.update(hard_exclusions)
            current.tags.difference_update(hard_exclusions)

        return current

    def _matches_active_constraints(
        self, match: RecommendationMatch, constraints: SearchConstraints
    ) -> bool:
        tags = SearchConstraints.tags_with_category(
            {tag.name for tag in match.item.tags.all()},
            match.item.category.name,
        )
        excluded = self._preferences().excluded_tags | set(constraints.excluded_tags)
        cost = self._minimum_payable(match.item)

        return (
            cost is not None
            and not tags & excluded
            and constraints.required_tags.issubset(tags)
            and (
                constraints.category is None
                or match.item.category.name.casefold() == constraints.category.casefold()
            )
            and (
                constraints.max_price is None
                or (cost is not None and cost <= constraints.max_price)
            )
            and (constraints.budget is None or constraints.budget.allows(cost))
        )

    def _select_previous_recommendation(
        self,
        interpretation: ConversationInterpretation,
        session_state: ConversationStatePayload,
    ) -> RecommendationMatch | None:
        previous = self._session_state.get_last_recommendation_ids()
        index = {
            "first": 0,
            "second": 1,
            "last": -1,
        }.get(interpretation.contextual_reference)

        if index is None or not previous or index >= len(previous):
            return None

        match = self.recommender.get_available_match(previous[index])

        return (
            match
            if match is not None
            and self._matches_active_constraints(match, self._search_constraints())
            else None
        )

    def _entity_response(
        self,
        entity: EntityResolution,
        preferences: Preferences,
        interpretation: ConversationInterpretation,
        *,
        budget: BudgetConstraint | None = None,
        clear_budget: bool = False,
    ) -> ChatbotResponse:
        self._response_purpose = (
            'nonfood' if entity.domain_status == 'NON_FOOD_OUT_OF_SCOPE' else 'clarification'
        )
        state = self._session_state.load_state().get("state", "COLLECTING_PREFERENCES")
        matches: list[RecommendationMatch] = []

        if entity.domain_status == "IN_CATALOG":
            return self._select_catalog_target(
                entity, preferences, interpretation, budget=budget, clear_budget=clear_budget
            )
        elif entity.domain_status == "NON_FOOD_OUT_OF_SCOPE":
            message = self._responses.nonfood(entity.requested_entity)
        elif entity.domain_status == "FOOD_BUT_NOT_AVAILABLE":
            template = self._responses.choose(
                'missing_food',
                (
                    "Aku belum menemukan {entity} sebagai pilihan menu di katalog kami. Mau mencari makanan atau minuman lain?",
                    "{entity} belum ditemukan di katalog. Mau melihat pilihan makanan atau minuman lainnya?",
                    "Untuk {entity}, belum ada pilihan yang kutemukan di menu kami. Kamu ingin mencari jenis makanan lain?",
                    "Pilihan {entity} belum tercatat di katalog ini. Aku bisa bantu mencari menu lainnya.",
                ),
            )
            message = template.format(entity=entity.requested_entity)
        elif entity.domain_status == "RESTAURANT_INFORMATION":
            message = "Untuk informasi layanan seperti parkir atau pengantaran, aku belum punya data yang terverifikasi. Silakan tanyakan kepada staf restoran. Aku bisa membantu memilih menu."
        elif entity.domain_status == "GENERAL_CONVERSATION":
            message = (
                "Kalau ingin memilih menu berikutnya, aku bisa bantu. Ingin makanan atau minuman apa?"
                if entity.requested_entity == 'menu sebelumnya'
                else "Kalau sedang lapar, aku bisa bantu memilih menu. Kamu ingin makanan seperti apa?"
            )
        else:
            message = f"Boleh jelaskan yang kamu maksud dengan {entity.requested_entity}? Sebutkan nama menu atau jenis makanan/minuman yang kamu cari."

        result: ChatbotResponse = {
            "message": message,
            "state": state,
            "preferences": self._response_preferences(preferences, state),
            "recommendations": matches,
            "quick_replies": [],
            "catalog_question": entity.domain_status == "IN_CATALOG",
        }

        return result

    def _select_catalog_target(
        self,
        entity: EntityResolution,
        preferences: Preferences,
        interpretation: ConversationInterpretation,
        *,
        budget: BudgetConstraint | None = None,
        clear_budget: bool = False,
    ) -> ChatbotResponse:
        old_focus = self._session_state.get_focus()
        identifier = interpretation.target_menu_id

        if identifier is None and len(entity.menu_ids) == 1:
            identifier = entity.menu_ids[0]

        match = self.recommender.get_available_match(identifier) if identifier is not None else None
        previous = self._search_constraints()
        bounds = None if clear_budget else budget or previous.budget
        maximum = (
            None
            if clear_budget
            else bounds.legacy_maximum if bounds is not None else previous.max_price
        )
        excluded = (
            previous.excluded_tags
            | frozenset(preferences.excluded_tags)
            | frozenset(interpretation.excluded_tags)
        )

        if match is None:
            return self._budget_clarification(
                preferences, self._unavailable_message(identifier, entity.requested_entity)
            )

        tags = SearchConstraints.tags_with_category(
            {tag.name for tag in match.item.tags.all()}, match.item.category.name
        )
        cost = self._minimum_payable(match.item)

        if cost is None:
            return self._budget_clarification(
                preferences, self._unavailable_message(match.item.pk, match.item.name)
            )

        if tags & excluded:
            return self._budget_clarification(
                preferences,
                f'Informasi {match.item.name} mencantumkan bahan yang ingin kamu hindari. Mau lihat pilihan lain?',
            )

        if (bounds is not None and not bounds.allows(cost)) or (
            maximum is not None and cost > maximum
        ):
            description = (
                bounds.description().replace(',00', '')
                if bounds is not None
                else 'maksimal ' + self._responses.money(Decimal(maximum))
            )

            return self._budget_clarification(
                preferences,
                f'{match.item.name} mulai dari {self._responses.money(cost)}. Budgetmu {description} per menu. Mau aku carikan pilihan lain yang sesuai?',
            )

        same_scope = (
            previous.category is None
            or previous.category.casefold() == match.item.category.name.casefold()
        ) and previous.required_tags.issubset(tags)
        constraints = SearchConstraints(
            previous.required_tags if same_scope else frozenset(),
            excluded,
            previous.category if same_scope and previous.category else match.item.category.name,
            maximum,
            previous.moods,
            budget=bounds,
            soft_target=previous.soft_target,
        )
        self._session_state.allow_requested([match.item.pk])
        self._session_state.remember_rejected(list(interpretation.rejected_menu_ids))
        self._session_state.save_search(constraints, update_required_tags=True)
        pool = self.recommender.rank(
            preferences,
            limit=ConversationSession.MAX_HISTORY,
            exclude_ids=self._session_state.get_explicit_rejections(),
            constraints=constraints,
        )
        self._session_state.set_candidates([candidate.item.pk for candidate in pool])
        self._session_state.set_focus(match.item.pk)
        self._session_state.set_last_question(None)
        self._session_state.record_recommendations(
            [match.item.pk], shown_ids=self._session_state.get_shown_ids() + [match.item.pk]
        )
        preferences.tags = set(constraints.required_tags)
        self._save(preferences, 'RECOMMENDING')
        switching = old_focus is not None and old_focus != match.item.pk
        self._response_purpose = 'switching' if switching else 'selection'
        message = self._responses.selection(match.item.name, switching=switching)

        if bounds is not None:
            message += (
                '\nBudgetmu '
                + bounds.description().replace(',00', '')
                + ' per menu. Varian dan tambahan bisa menambah biaya.'
            )

        return {
            'message': message,
            'state': 'RECOMMENDING',
            'preferences': self._response_preferences(preferences, 'RECOMMENDING'),
            'active_search': constraints.to_dict(),
            'recommendations': [match],
            'quick_replies': [self._quick_reply('Cari menu lain', 'yang lain', action='more')],
            'catalog_question': True,
        }

    def _named_price_question(self, message: str) -> ChatbotResponse | None:
        """An informational price lookup does not select a menu or change scope."""
        text = normalize_text(message)

        if re.search(r'\b(?:alergi|allergy|allergic|alergen)\b', text):
            return None

        question = re.fullmatch(
            r'(?:berapa(?: sih)? (?:harga|harganya) (.+?)|(?:harga|harganya) (.+?) berapa)[?!.]*',
            text,
        )

        if question is None:
            return None

        target = (question.group(1) or question.group(2)).strip(' ?!.')
        entity = self._entity_resolver.resolve(target)

        if entity is None or entity.domain_status != 'IN_CATALOG' or len(entity.menu_ids) != 1:
            return None

        # Quantities, options and extra clauses need their normal interpretation.
        if entity.modifiers and entity.modifiers.strip(' ?!.,'):
            return None

        self._session_state.expire_dialog(touch=False)
        item = self.recommender.get_available_match(entity.menu_ids[0])
        cost = self._minimum_payable(item.item) if item is not None else None
        text = (
            f'{item.item.name} mulai dari {self._responses.money(cost)}. '
            'Harga akhirnya tergantung varian dan tambahan yang kamu pilih.'
            if cost is not None
            else self._unavailable_message(entity.menu_ids[0], entity.requested_entity)
        )
        result = self._budget_clarification(self._preferences(), text)
        self._response_purpose, self._response_intent = 'help', ConversationIntent.HELP
        self._context_action = 'CONTINUE_CONTEXT'

        return result

    def _budget_clarification(self, preferences: Preferences, message: str) -> ChatbotResponse:
        self._response_purpose = 'clarification'
        state = self._session_state.load_state().get("state", "COLLECTING_PREFERENCES")

        return {
            "message": message,
            "state": state,
            "preferences": self._response_preferences(preferences, state),
            "active_search": self._search_constraints().to_dict(),
            "recommendations": [],
            "quick_replies": [],
        }

    def _budget_response(
        self,
        request: BudgetRequest,
        text: str,
        preferences: Preferences,
        interpretation: ConversationInterpretation,
        *,
        entity: EntityResolution | None = None,
    ) -> ChatbotResponse:
        if request.clarification:
            return self._budget_clarification(preferences, request.clarification)

        previous = self._search_constraints()
        bounds = request.constraint
        target = (
            previous.soft_target
            if request.kind in {'cheaper', 'expensive'}
            else request.soft_target
        )

        # A new explicit amount replaces the whole old range. A combined range
        # must be stated in one message. Relative cheaper/expensive requests
        # below still intersect existing hard bounds rather than relaxing them.
        if request.kind in {"cheaper", "expensive"}:
            ids = self._session_state.get_last_recommendation_ids()
            reference = interpretation.contextual_reference

            if reference and ids:
                index = {"first": 0, "second": 1, "last": -1}[reference]
                ids = [ids[index]] if index < len(ids) else []

            anchors = [
                cost
                for identifier in ids
                if (match := self.recommender.get_available_match(identifier)) is not None
                and (cost := self._minimum_payable(match.item)) is not None
            ]

            if not anchors or len(set(anchors)) != 1:
                return self._budget_clarification(
                    preferences,
                    "Lebih murah atau mahal dibanding menu yang mana? Sebutkan ‘yang pertama’, ‘yang kedua’, atau berikan batas harga.",
                )

            anchor = anchors[0]

            try:
                relative = (
                    BudgetConstraint(maximum=anchor, maximum_inclusive=False)
                    if request.kind == "cheaper"
                    else BudgetConstraint(minimum=anchor, minimum_inclusive=False)
                )
                existing = previous.budget or BudgetConstraint(
                    maximum=Decimal(previous.max_price) if previous.max_price is not None else None
                )
                bounds = existing.intersect(relative)
            except ValueError:
                return self._budget_clarification(
                    preferences,
                    "Permintaan harga relatif bertentangan dengan batas aktif. Ubah batas harga secara eksplisit terlebih dahulu.",
                )
        elif request.kind in {"affordable", "cheapest"}:
            bounds = previous.budget
        elif request.kind == "clear":
            bounds = None

        if request.kind in {'cheaper', 'expensive', 'affordable', 'cheapest'} or (
            request.kind == 'approximate' and entity is None
        ):
            self._session_state.set_entity_ids([])

        if request.kind == 'approximate' and entity is None:
            self._session_state.set_focus(None)
            self._response_intent = ConversationIntent.UPDATE_BUDGET

        if entity is not None:
            if request.kind == 'approximate':
                self._session_state.save_search(
                    SearchConstraints(
                        previous.required_tags,
                        previous.excluded_tags,
                        previous.category,
                        moods=previous.moods,
                        soft_target=target,
                    )
                )

            result = self._entity_response(
                entity,
                preferences,
                interpretation,
                budget=bounds,
                clear_budget=request.kind == 'clear',
            )

            if result['recommendations']:
                selected = self._search_constraints()
                selected = SearchConstraints(
                    selected.required_tags,
                    selected.excluded_tags,
                    selected.category,
                    selected.max_price,
                    selected.moods,
                    budget=selected.budget,
                    soft_target=target,
                )
                self._session_state.save_search(selected)
                result['active_search'] = selected.to_dict()
            elif request.kind == 'approximate':
                self._session_state.save_search(previous)

            return result

        if bounds is not None and interpretation.tags and text.startswith(("ada ", "apakah ada ")):
            interpretation.intent = ConversationIntent.CATALOG_QUESTION
            interpretation.catalog_tags = set(interpretation.tags)

        if interpretation.intent == ConversationIntent.CATALOG_QUESTION and bounds is not None:
            result = self._answer_catalog_question(preferences, interpretation, text, budget=bounds)
            result["message"] += (
                "\nBudgetmu "
                + bounds.description().replace(",00", "")
                + " per menu. Varian dan tambahan bisa menambah biaya."
            )

            return result

        has_food_change = bool(
            interpretation.tags
            or interpretation.excluded_tags
            or interpretation.soft_excluded_tags
            or interpretation.category
            or interpretation.moods
        )
        updated = Preferences.from_dict(preferences.to_dict())

        if has_food_change:
            updated = self._apply_interpretation(updated, interpretation)

        if request.kind in {"affordable", "cheapest"}:
            updated.prefer_affordable = True

        merged = (
            self._constraints_for_interpretation(
                interpretation, self._session_state.load_state().get('follow_up')
            )
            if has_food_change
            else previous
        )
        constraints = SearchConstraints(
            required_tags=merged.required_tags,
            excluded_tags=merged.excluded_tags,
            category=merged.category,
            max_price=(
                (None if request.kind in {"clear", "approximate"} else previous.max_price)
                if bounds is None
                else bounds.legacy_maximum
            ),
            moods=merged.moods,
            budget=bounds,
            soft_target=target,
        )
        self._session_state.save_search(constraints, update_required_tags=True)

        if (
            request.kind == "clear"
            and not self._has_preferences(updated)
            and not constraints.required_tags
        ):
            result = self._question()
            result["message"] = "Batas harga sudah dihapus. " + result["message"]

            return result

        if self._semantic_query is not None:
            self._session_state.set_focus(None)

        result = self._recommend(
            updated, text, constraints=constraints, cheapest=request.kind == "cheapest"
        )
        self._response_purpose = 'budget' if result['recommendations'] else 'empty'

        if constraints.budget is not None:
            result[
                "message"
            ] += "\nHarga yang dicek sudah termasuk varian wajib termurah. Varian lain atau tambahan bisa menambah totalnya."

        if request.kind == "clear":
            result["message"] = "Batas harga sudah dihapus.\n" + result["message"]

        if not result["recommendations"]:
            budget_text = (
                constraints.budget.description()
                if constraints.budget is not None
                else (
                    f"maksimal Rp{constraints.max_price}"
                    if constraints.max_price is not None
                    else ""
                )
            )
            result["quick_replies"] = [
                self._quick_reply("Ubah batas harga", "hapus batas budget"),
                self._quick_reply("Termurah sesuai batas", "lihat menu termurah"),
                self._quick_reply("Makanan sesuai batas", f"ingin makanan {budget_text}"),
                self._quick_reply("Minuman sesuai batas", f"ingin minuman {budget_text}"),
            ]

        return result

    def _context_acknowledgement(self, context: UserContext) -> str:
        phrases = {
            "sad": "Semoga harimu membaik, ya.",
            "stressed": "Kedengarannya harimu cukup berat. Semoga ada kesempatan beristirahat.",
            "frustrated": "Kedengarannya sedang membuatmu kesal.",
            "disappointed": "Sayang sekali harimu terasa mengecewakan.",
            "happy": "Senang mendengar kabar baiknya!",
        }

        for emotion, phrase in phrases.items():
            if emotion in context.emotions:
                alternatives = {
                    'sad': (
                        'Semoga hari ini terasa lebih baik untukmu.',
                        'Semoga ada hal kecil yang membuat harimu lebih baik.',
                    ),
                    'stressed': (
                        'Semoga kamu mendapat waktu untuk beristirahat sejenak.',
                        'Kedengarannya sedang banyak yang kamu hadapi.',
                    ),
                    'frustrated': (
                        'Kedengarannya itu cukup menjengkelkan.',
                        'Semoga keadaan segera terasa lebih baik.',
                    ),
                    'disappointed': (
                        'Kedengarannya tidak sesuai harapanmu.',
                        'Semoga harimu berikutnya terasa lebih baik.',
                    ),
                    'happy': ('Ikut senang mendengarnya!', 'Semoga suasana baiknya berlanjut!'),
                }

                return self._responses.choose('empathy', (phrase, *alternatives[emotion]))

        if "tired" in context.physical:
            return "Setelah aktivitas yang melelahkan, aku bantu melihat pilihan sesuai seleramu."

        if "hurry" in context.situations:
            return "Kalau sedang terburu-buru, waktu penyajian bisa dipastikan ke staf."

        return ""

    def _clear_temporary_moods(self) -> None:
        stored = self._session_state.load_state()
        preferences = self._preferences()
        inferred = set(self.session.pop(ConversationSession.INFERRED_KEY, []))

        if not preferences.moods and not preferences.mood_tags and not inferred:
            return

        preferences.moods.clear()
        preferences.mood_tags.clear()
        preferences.tags.difference_update(inferred)

        if stored:
            self._save(preferences, stored.get("state", "COLLECTING_PREFERENCES"))

        search = self._search_constraints()
        self._session_state.save_search(
            SearchConstraints(
                search.required_tags - inferred,
                search.excluded_tags,
                search.category,
                search.max_price,
                frozenset(),
                budget=search.budget,
                soft_target=search.soft_target,
            )
        )

    @staticmethod
    def _minimum_payable(item: MenuItem) -> Decimal | None:
        return MenuSelection.minimum_payable(item)

    @staticmethod
    def _unavailable_message(identifier: int | None, requested_name: str) -> str:
        item = (
            MenuItem.objects.filter(pk=identifier).select_related('category').first()
            if identifier is not None
            else None
        )

        if item is None:
            return f'Aku belum menemukan {requested_name} di katalog saat ini. Nama menu apa yang ingin kamu cari?'

        if not item.is_active or not item.is_available or not item.category.is_active:
            return f'{item.name} belum tersedia saat ini. Mau aku carikan pilihan {item.category.name.lower()} lain?'

        return (
            f'Pilihan varian wajib untuk {item.name} belum lengkap saat ini. Mau memilih menu lain?'
        )

    def _plan_selection(self, item: MenuItem, operation: str) -> list[dict[str, int]] | None:
        data = self._session_state.contexts()
        pending_role = item.category.name in data['plan']['unresolved_roles']

        if (
            not data['overall']
            and not data['plan']['entries']
            and self._requested_quantity is None
            and operation != 'ADD_TO_CONTEXT'
            and not pending_role
        ):
            return None

        if 'per_person_budget' in data['overall'] and 'person_count' not in data['overall']:
            self._context_block = 'Budget per orang sudah dicatat. Berapa orang yang akan makan?'

            return None

        entries = deepcopy(data['plan']['entries'])
        quantity = self._requested_quantity or data['plan'].get('role_quantities', {}).get(
            item.category.name, 1
        )

        if self._requested_quantity is None and operation != 'ADD_TO_CONTEXT':
            same_role = [
                entry
                for entry in entries
                if MenuItem.objects.filter(
                    pk=entry['menu_id'], category_id=item.category_id
                ).exists()
            ]

            if len(same_role) == 1:
                quantity = same_role[0]['quantity']

        if operation == 'ADD_TO_CONTEXT' and not entries:
            focused = self._session_state.get_focus()

            if focused is not None and focused != item.pk:
                entries.append(
                    {'context_id': data['active']['id'], 'menu_id': focused, 'quantity': 1}
                )

        focused = self._session_state.get_focus()

        if operation == 'ADD_TO_CONTEXT':
            identical = next((entry for entry in entries if entry['menu_id'] == item.pk), None)

            if identical is not None:
                identical['quantity'] += quantity

                if identical['quantity'] > 99:
                    self._context_block = 'Jumlah satu menu dalam rencana maksimal 99. Sebutkan jumlah baru yang lebih kecil.'

                    return None

                _, error = self._plan_facts(entries)

                if error:
                    self._context_block = error

                    return None

                return entries

        if operation == 'CORRECT_PREVIOUS' and any(
            entry['menu_id'] == focused for entry in entries
        ):
            entries = [entry for entry in entries if entry['menu_id'] != focused]
        elif operation != 'ADD_TO_CONTEXT':
            # A new choice fills/replaces one category role, never silently buys all mentions.
            entries = [
                entry
                for entry in entries
                if not MenuItem.objects.filter(
                    pk=entry['menu_id'], category_id=item.category_id
                ).exists()
            ]

        if len(entries) >= 8:
            self._context_block = 'Rencana ini sudah memiliki delapan item. Pilih item yang ingin diganti sebelum menambahkan lagi.'

            return None

        entries.append(
            {'context_id': data['active']['id'], 'menu_id': item.pk, 'quantity': quantity}
        )
        _, error = self._plan_facts(entries, incoming=True)

        if error:
            self._context_block = error

            return None

        return entries

    def _plan_facts(
        self,
        entries: list[dict[str, int]],
        *,
        incoming: bool = False,
    ) -> tuple[Decimal | None, str | None]:
        """Read the exact draft's current payable facts without rebuilding its roles.

        During initial selection only the incoming entry has not acquired its
        new context yet. Final validation checks every committed context scope.
        """
        data = self._session_state.contexts()
        frames = {frame['id']: frame for frame in [data['active'], *data['previous']]}
        total = Decimal(0)
        category_totals: dict[str, Decimal] = {}
        per_person_maximum = Decimal(0)
        people = data['overall'].get('person_count')

        for position, entry in enumerate(entries):
            match = self.recommender.get_available_match(entry['menu_id'])

            if (
                match is not None
                and {tag.name for tag in match.item.tags.all()}
                & self._session_state.global_exclusions()
            ):
                return (
                    None,
                    'Ada item rencana dengan bahan yang kamu hindari. Pilih pengganti dan konfirmasikan bahan serta risiko kontak silang kepada staf.',
                )

            cost = self._minimum_payable(match.item) if match is not None else None

            if cost is None:
                return None, self._unavailable_message(entry['menu_id'], 'pilihan dalam rencana')

            if not (incoming and position == len(entries) - 1):
                frame = frames.get(entry['context_id']) or data['plan'].get('scopes', {}).get(
                    str(entry['context_id'])
                )

                if frame is None:
                    return (
                        None,
                        'Konteks batas pilihan lama sudah tidak tersedia. Sebutkan kembali pilihan dan batasnya sebelum melanjutkan rencana.',
                    )

                active = entry['context_id'] == data['active']['id']
                constraints = (
                    self._search_constraints()
                    if active
                    else SearchConstraints.from_dict(frame['constraints'])
                )
                focus = self._session_state.get_focus() if active else frame['focused_item_id']

                if entry['menu_id'] != focus and frame['item_excluded_tags']:
                    constraints = SearchConstraints(
                        constraints.required_tags,
                        constraints.excluded_tags - set(frame['item_excluded_tags']),
                        constraints.category,
                        constraints.max_price,
                        constraints.moods,
                        budget=constraints.budget,
                        soft_target=constraints.soft_target,
                    )

                # Reuse the authoritative local filter, including category/tag
                # semantics, rather than inventing a separate plan filter.
                candidates = self.recommender.rank(
                    Preferences(),
                    limit=ConversationSession.MAX_HISTORY,
                    constraints=constraints,
                    include_unscored=True,
                )

                if entry['menu_id'] not in {candidate.item.pk for candidate in candidates}:
                    return (
                        None,
                        'Data menu berubah atau ada pilihan rencana yang tidak lagi memenuhi batas pencariannya. Pilih pengganti atau ubah batas yang dimaksud.',
                    )

            total += cost * entry['quantity']
            category_totals[match.item.category.name] = (
                category_totals.get(match.item.category.name, Decimal(0)) + cost * entry['quantity']
            )

            if people:
                per_person_maximum += cost * ((entry['quantity'] + people - 1) // people)

        for category, amount in data['overall'].get('category_budgets', {}).items():
            if category_totals.get(category, Decimal(0)) > Decimal(amount):
                return None, (
                    'Harga minimum pilihan '
                    + category.lower()
                    + ' '
                    + self._responses.money(category_totals[category])
                    + ' melebihi alokasi '
                    + self._responses.money(Decimal(amount))
                    + '. Pilihan sebelumnya tetap tersimpan. Mau mengganti pilihan kategori itu?'
                )

        limits = (
            [Decimal(data['overall']['total_budget'])] if 'total_budget' in data['overall'] else []
        )

        if 'per_person_budget' in data['overall'] and people:
            limits.append(Decimal(data['overall']['per_person_budget']) * people)

            if data['plan'].get('serving_mode') == 'individual' and per_person_maximum > Decimal(
                data['overall']['per_person_budget']
            ):
                return (
                    None,
                    'Pembagian porsi masing-masing belum memenuhi budget per orang. Ubah menu, jumlah porsi atau pembagiannya; aku belum dapat memastikan alokasi campuran ini.',
                )

        maximum = min(limits) if limits else None

        if maximum is not None and total > maximum:
            return None, (
                'Minimal harga rencana ini '
                + self._responses.money(total)
                + ', melebihi budget total '
                + self._responses.money(maximum)
                + '. Pilihan sebelumnya tetap tersimpan. Mau mencari pengganti yang lebih terjangkau?'
            )

        return total, None

    def _eligible_for_plan(self, matches: list[RecommendationMatch]) -> list[RecommendationMatch]:
        """Apply overall eligibility to the full local pool, before top-three ranking.

        A candidate is an alternative for its category role unless the user
        explicitly adds it. Probing never mutates the draft plan or its reply.
        """

        if ConversationSession.CONTEXTS_KEY not in self.session:
            return matches

        data = self._session_state.contexts()

        if (
            not data['overall']
            and not data['plan']['entries']
            and not data['plan'].get('role_quantities')
            and self._requested_quantity is None
            and self._context_action != 'ADD_TO_CONTEXT'
        ):
            return matches

        saved_block = self._context_block

        try:
            return [
                match
                for match in matches
                if self._plan_selection(match.item, self._context_action) is not None
            ]
        finally:
            self._context_block = saved_block

    def _apply_plan_delta(self, match: RecommendationMatch | None, budget: BudgetRequest) -> bool:
        before = deepcopy(self._session_state.contexts())
        handled = self._stage_plan_delta(match, budget)

        if handled and self._context_action == 'CLARIFY':
            self.session[ConversationSession.CONTEXTS_KEY] = before
            self._plan_error = True

        return handled

    def _stage_plan_delta(self, match: RecommendationMatch | None, budget: BudgetRequest) -> bool:
        """Stage bounded metadata/quantity updates in this reply's existing draft."""
        delta = self._plan_delta
        data = self._session_state.contexts()

        if delta.clarification:
            self._context_block, self._context_action = delta.clarification, 'CLARIFY'

            return True

        if (
            delta.target_role
            and match is not None
            and delta.target_role != match.item.category.name
        ):
            self._context_block = (
                'Menu itu bukan bagian kategori '
                + delta.target_role
                + '. Sebutkan menu untuk kategori tersebut.'
            )
            self._context_action = 'CLARIFY'

            return True

        if delta.cancel_role:
            role = delta.cancel_role
            identifiers = set(
                MenuItem.objects.filter(category__name=role).values_list('pk', flat=True)
            )
            entries = [
                entry for entry in data['plan']['entries'] if entry['menu_id'] not in identifiers
            ]
            self._session_state.commit_plan(entries)
            data['plan']['unresolved_roles'] = [
                value for value in data['plan']['unresolved_roles'] if value != role
            ]
            data['plan'].get('role_quantities', {}).pop(role, None)

            if data['overall']:
                data['overall']['requested_categories'] = [
                    value
                    for value in data['overall'].get('requested_categories', [])
                    if value != role
                ]
                allocations = data['overall'].get('category_budgets', {})
                allocations.pop(role, None)

                if not allocations:
                    data['overall'].pop('category_budgets', None)

                if not set(data['overall']) & {
                    'total_budget',
                    'per_person_budget',
                    'category_budgets',
                }:
                    data['overall'].clear()

            self._plan_changed = True
            self._context_action = 'CORRECT_PREVIOUS'
            self._context_block = (
                'Peran '
                + role
                + ' dibatalkan. Pilihan kategori lain dan budget yang masih berlaku tetap tersimpan.'
            )

            return True

        if delta.person_count is not None:
            if not data['overall']:
                self._context_block = 'Jumlah orang ini untuk rencana yang mana? Sebutkan budget total atau per orang terlebih dahulu.'
                self._context_action = 'CLARIFY'

                return True

            data['overall']['person_count'] = delta.person_count
            self._response_intent = ConversationIntent.UPDATE_PLAN
            self._plan_changed = True
            self._context_action = 'CORRECT_PREVIOUS'
            self._context_block = f'Jumlah orang sekarang {delta.person_count}. Nominal budget dan jumlah item sebelumnya tetap.'

            if data['plan'].get('serving_mode', 'unspecified') == 'unspecified':
                self._context_block += ' Apakah porsinya masing-masing atau berbagi?'

        if delta.serving_mode is not None:
            data['plan']['serving_mode'] = delta.serving_mode
            self._plan_changed = True

        if delta.role_quantities:
            quantities = {**data['plan'].get('role_quantities', {}), **delta.role_quantities}

            if len(quantities) > 8:
                self._context_block, self._context_action = (
                    'Rencana maksimal memiliki delapan kategori. Batalkan satu kategori dahulu.',
                    'CLARIFY',
                )

                return True

            data['plan']['role_quantities'] = quantities
            entries = deepcopy(data['plan']['entries'])

            for role, quantity in delta.role_quantities.items():
                identifiers = set(
                    MenuItem.objects.filter(category__name=role).values_list('pk', flat=True)
                )
                selected = [entry for entry in entries if entry['menu_id'] in identifiers]

                if len(selected) == 1:
                    selected[0]['quantity'] = quantity
                elif len(selected) > 1:
                    self._context_block, self._context_action = (
                        'Kategori itu memiliki beberapa menu terpilih. Sebutkan nama menu yang jumlahnya ingin diubah.',
                        'CLARIFY',
                    )

                    return True
                elif role not in data['plan']['unresolved_roles']:
                    data['plan']['unresolved_roles'].append(role)

            self._planned_entries, self._plan_update_only, self._plan_changed = entries, True, True

            if budget.kind == 'none':
                self._context_block = (
                    'Jumlah kategori sudah dicatat. Pilih menu untuk kategori yang belum terisi: '
                    + (', '.join(data['plan']['unresolved_roles']) or 'tidak ada')
                    + '.'
                )
                self._context_action = 'CORRECT_PREVIOUS'

                return True

        if (
            delta.category_budgets
            or delta.total_budget is not None
            and delta.per_person_budget is not None
            or delta.total_budget is not None
            and delta.role_quantities
            or delta.per_person_budget is not None
            and delta.serving_mode == 'individual'
            and match is None
        ):
            if (
                len(set(data['overall'].get('category_budgets', {})) | set(delta.category_budgets))
                > 8
                or len(
                    set(data['overall'].get('requested_categories', []))
                    | set(delta.requested_roles)
                )
                > 8
            ):
                self._context_block, self._context_action = (
                    'Rencana maksimal memiliki delapan kategori alokasi.',
                    'CLARIFY',
                )

                return True

            try:
                for amount in [
                    *delta.category_budgets.values(),
                    delta.total_budget,
                    delta.per_person_budget,
                ]:
                    if amount is not None:
                        BudgetConstraint(maximum=Decimal(amount))
            except (ValueError, ArithmeticError):
                self._context_block, self._context_action = (
                    'Sebutkan alokasi valid antara Rp0 dan Rp1.000.000.',
                    'CLARIFY',
                )

                return True

            if not data['overall']:
                self._session_state.archive_context(None)

            overall = data['overall']
            overall.update(explicitly_declared=True, plan_id=data['plan']['id'])

            if delta.total_budget is not None:
                overall['total_budget'] = str(delta.total_budget)

            if delta.per_person_budget is not None:
                overall['per_person_budget'] = str(delta.per_person_budget)

            counts = [
                mention.value for mention in budget.numeric_roles if mention.role == 'PERSON_COUNT'
            ]

            if counts:
                if (
                    len(counts) != 1
                    or counts[0] != counts[0].to_integral_value()
                    or not 1 <= counts[0] <= 99
                ):
                    self._context_block, self._context_action = (
                        'Sebutkan satu jumlah orang yang utuh antara 1 dan 99.',
                        'CLARIFY',
                    )

                    return True

                overall['person_count'] = int(counts[0])

            if delta.category_budgets:
                overall['category_budgets'] = {
                    **overall.get('category_budgets', {}),
                    **delta.category_budgets,
                }

                if (
                    delta.implicit_total is not None
                    and 'total_budget' not in overall
                    and 'per_person_budget' not in overall
                ):
                    overall['total_budget'] = str(delta.implicit_total)

            roles = list(
                dict.fromkeys(
                    overall.get('requested_categories', [])
                    + list(delta.category_budgets)
                    + list(delta.requested_roles)
                )
            )
            overall['requested_categories'] = roles
            chosen = set(
                MenuItem.objects.filter(
                    pk__in=[entry['menu_id'] for entry in data['plan']['entries']]
                ).values_list('category__name', flat=True)
            )
            data['plan']['unresolved_roles'] = [role for role in roles if role not in chosen]
            self._plan_changed = True
            self._context_action = 'CORRECT_PREVIOUS'
            self._context_block = (
                'Batas alokasi rencana sudah dicatat secara terpisah. Pilihan lain tetap tersimpan; kategori yang belum diisi: '
                + (', '.join(data['plan']['unresolved_roles']) or 'tidak ada')
                + '.'
            )

            return True

        if delta.quantity is not None:
            quantity = delta.quantity

            if delta.per_person_quantity:
                count = data['overall'].get('person_count')

                if count is None:
                    self._context_block, self._context_action = (
                        'Berapa jumlah orang untuk porsi masing-masing ini?',
                        'CLARIFY',
                    )

                    return True

                quantity *= count

            if quantity > 99:
                self._context_block, self._context_action = (
                    'Jumlah satu menu maksimal 99. Sebutkan jumlah yang lebih kecil.',
                    'CLARIFY',
                )

                return True

            self._requested_quantity = quantity

            if match is None and not delta.quantity_only:
                entity = self._entity_resolver.resolve(delta.entity_text or '')
                names = list(
                    MenuItem.objects.filter(
                        pk__in=entity.menu_ids if entity else (),
                        is_active=True,
                        is_available=True,
                        category__is_active=True,
                    )
                    .order_by('name')
                    .values_list('name', flat=True)[:8]
                )
                self._context_block = (
                    f'Untuk {quantity} item, pilih satu nama menu yang dimaksud'
                    + (': ' + ', '.join(names) if names else '')
                    + '.'
                )
                self._context_action = 'CLARIFY'

                return True

            if delta.quantity_only:
                identifier = match.item.pk if match is not None else self._session_state.get_focus()

                if delta.target_role and (
                    match is None or match.item.category.name != delta.target_role
                ):
                    candidates = list(
                        MenuItem.objects.filter(
                            pk__in=[entry['menu_id'] for entry in data['plan']['entries']],
                            category__name=delta.target_role,
                        ).values_list('pk', flat=True)
                    )
                    identifier = candidates[0] if len(candidates) == 1 else None

                target = (
                    self.recommender.get_available_match(identifier)
                    if identifier is not None
                    else None
                )

                if target is None:
                    self._context_block, self._context_action = (
                        'Jumlah ini untuk menu yang mana? Sebutkan satu nama menu yang sudah dipilih.',
                        'CLARIFY',
                    )

                    return True

                entries = deepcopy(data['plan']['entries'])
                chosen = next((entry for entry in entries if entry['menu_id'] == identifier), None)

                if chosen is None:
                    if identifier != self._session_state.get_focus():
                        self._context_block, self._context_action = (
                            'Menu itu belum dipilih dalam rencana ini. Pilih menunya dahulu.',
                            'CLARIFY',
                        )

                        return True

                    entries.append(
                        {
                            'context_id': data['active']['id'],
                            'menu_id': identifier,
                            'quantity': quantity,
                        }
                    )
                else:
                    chosen['quantity'] = quantity

                self._planned_entries, self._plan_update_only, self._plan_changed = (
                    entries,
                    True,
                    True,
                )
                self._context_action = 'CORRECT_PREVIOUS'
                self._context_block = f'Jumlah {target.item.name} sekarang {quantity}. Jumlah orang dan budget sebelumnya tetap berlaku.'

                return True

        if self._context_block:
            return True

        if delta.serving_mode is not None and match is None and delta.quantity is None:
            self._context_block = (
                'Porsi dicatat untuk '
                + ('masing-masing orang' if delta.serving_mode == 'individual' else 'berbagi')
                + '. Sebutkan menu dan jumlahnya agar pembagian budget bisa diperiksa.'
            )

            return True

        return False

    def _revise_active_preferences(self, text: str) -> bool:
        """Apply an explicit local tag delta using existing operation semantics."""

        if re.search(r'\b(?:alergi|allergy|allergic|alergen)\b', text):
            return False

        scope = re.search(r'\s+(?:untuk|pada)\s+(.+?)\s+(?:tadi|sebelumnya)\s*$', text)
        global_scope = re.search(
            r'\s+(?:untuk|pada)\s+(?:semua|seluruh)\s+(?:pilihan|pencarian|menu)\s*$', text
        )
        command = (
            text[: scope.start()]
            if scope
            else text[: global_scope.start()] if global_scope else text
        )
        revision = self.interpreter._tag_revision(command)

        if (
            revision is None
            or len(revision.operations) != 1
            or revision.operations[0].action not in {'DROP', 'RELAX'}
        ):
            return False

        # A named menu rejection is handled by the existing catalog/plan path.
        entity = self._entity_resolver.resolve(command)

        if entity is not None and entity.domain_status in {
            'IN_CATALOG',
            'REJECTED_CATALOG',
            'AMBIGUOUS_CATALOG',
        }:
            return False

        data = self._session_state.contexts()
        operation = revision.operations[0]
        tags = set(operation.tags)
        self._context_action = 'CORRECT_PREVIOUS'

        if scope:
            categories = {
                normalize_text(name): name
                for name in Category.objects.filter(is_active=True).values_list('name', flat=True)
            }
            category = categories.get(scope[1])

            if category is None or (
                data['active']['category'] != category
                and not self._session_state.restore_context(category)
            ):
                self._context_action = 'CLARIFY'
                self._context_block = 'Konteks kategori itu tidak tersedia di pilihan sebelumnya. Sebutkan kategori untuk pencarian baru, ya.'

                return True

        if operation.action == 'RELAX' and data['active']['legacy_unresolved'] and scope is None:
            self._context_action = 'CLARIFY'
            self._context_block = 'Cakupan larangan lama belum jelas. Sebutkan kategori yang ingin diperbarui sebelum melepas bahan yang dihindari.'

            return True

        previous = self._search_constraints()
        global_tags = tags & self._session_state.global_exclusions()

        if operation.action == 'RELAX' and global_tags:
            if data['safety']['verification_required']:
                self._context_action = 'CLARIFY'
                self._context_block = 'Batas bahan untuk keselamatan tetap berlaku. Konfirmasikan bahan dan risiko kontak silang kepada staf; perubahan selera ini tidak membuktikan menu aman.'
                self._plan_error = True

                return True

            if global_scope is None:
                self._context_action = 'CLARIFY'
                self._context_block = 'Larangan ini berlaku untuk semua pencarian. Jika ingin melepasnya, sebutkan bahwa bahan tersebut boleh untuk semua pencarian.'
                self._plan_error = True

                return True

            data['safety']['excluded_tags'] = sorted(set(data['safety']['excluded_tags']) - tags)

            # Explicit all-search relaxation revises every owned snapshot, so
            # restoring an old category cannot resurrect this ordinary ban.
            def relax_payload(payload: dict) -> None:
                if 'excluded_tags' in payload:
                    payload['excluded_tags'] = sorted(set(payload['excluded_tags']) - tags)

                if 'soft_excluded_tags' in payload:
                    payload['soft_excluded_tags'] = sorted(
                        set(payload['soft_excluded_tags']) - tags
                    )

            for frame in [data['active'], *data['previous']]:
                relax_payload(frame['constraints'])
                frame['item_excluded_tags'] = sorted(set(frame['item_excluded_tags']) - tags)

                for key in (ConversationSession.SEARCH_KEY, ConversationSession.STATE_KEY):
                    if isinstance(frame['projection'].get(key), dict):
                        relax_payload(frame['projection'][key])

            for saved in data['plan'].get('scopes', {}).values():
                relax_payload(saved['constraints'])
                saved['item_excluded_tags'] = sorted(set(saved['item_excluded_tags']) - tags)
        elif global_scope is not None:
            self._context_action = 'CLARIFY'
            self._context_block = 'Revisi selera ini berlaku pada pencarian aktif. Untuk pilihan lama, sebutkan kategori yang ingin diperbarui.'

            return True

        required, excluded = set(previous.required_tags), set(previous.excluded_tags)
        preferences = self._session_state.load_preferences()
        was_present = bool(
            tags
            & (
                required | preferences.tags
                if operation.action == 'DROP'
                else excluded | preferences.excluded_tags | preferences.soft_excluded_tags
            )
        )

        if operation.action == 'DROP':
            required.difference_update(tags)
            preferences.tags.difference_update(tags)
        else:
            excluded.difference_update(tags)
            preferences.excluded_tags.difference_update(tags)
            preferences.soft_excluded_tags.difference_update(tags)

        excluded.update(self._session_state.global_exclusions())
        criteria = SearchConstraints(
            frozenset(required),
            frozenset(excluded),
            previous.category,
            previous.max_price,
            previous.moods,
            budget=previous.budget,
            soft_target=previous.soft_target,
        )
        self._session_state.save_search(criteria, update_required_tags=True)
        self._save(
            preferences, self._session_state.load_state().get('state', 'COLLECTING_PREFERENCES')
        )
        data['active']['item_excluded_tags'] = sorted(
            set(data['active']['item_excluded_tags']) & excluded
        )
        self._plan_changed = bool(data['plan']['entries'])
        self._response_purpose, self._response_intent = (
            'removal',
            ConversationIntent.REMOVE_PREFERENCES,
        )
        labels = ', '.join(tag_label(tag) for tag in sorted(tags))
        self._context_block = (
            'Permintaan ' + labels + ' sudah dilepas dari pencarian aktif.'
            if operation.action == 'DROP'
            else 'Larangan '
            + labels
            + ' sudah dilepas dari cakupan yang kamu tentukan; bahan itu tidak otomatis menjadi pilihan wajib.'
        )

        if not was_present:
            self._context_block = (
                'Tidak ada '
                + ('permintaan ' if operation.action == 'DROP' else 'larangan ')
                + labels
                + ' pada pencarian aktif. Pilihan dan batas lainnya tetap tersimpan.'
            )

        if data['safety']['verification_required']:
            self._context_block += (
                ' Batas bahan untuk keselamatan tetap berlaku; konfirmasikan kepada staf.'
            )

        return True

    @staticmethod
    def _is_context_summary(message: str) -> bool:
        text = normalize_text(message).strip(' .!?')

        return bool(
            re.fullmatch(
                r'(?:lagi cariin apa(?: buat aku)?|(?:apa|menu apa) yang (?:sedang|lagi) (?:kamu |anda )?(?:carikan|cari|cariin)(?: buat aku| untuk aku)?|ringkas(?:an)? (?:pilihan|pencarian|konteks)(?:ku| saya| aku)?|sedang (?:cari|mencari) apa(?: buat aku)?)',
                text,
            )
        )

    def _context_summary(self) -> ChatbotResponse:
        """Public facts only; read from a validated disposable draft, never archives."""
        graph = self._session_state.contexts()
        criteria = self._search_constraints()
        category = criteria.category
        parts = (
            ['Sekarang aku sedang mencarikan ' + (category.lower() if category else 'menu') + '.']
            if (
                category
                or criteria.required_tags
                or criteria.excluded_tags
                or criteria.budget
                or criteria.max_price is not None
                or criteria.soft_target is not None
            )
            else ['Belum ada pencarian menu aktif.']
        )
        tags = criteria.required_tags - (
            {'drink'} if category == 'Minuman' else {'snack'} if category == 'Camilan' else set()
        )

        if tags:
            parts.append(
                'Selera yang diminta: ' + ', '.join(tag_label(tag) for tag in sorted(tags)) + '.'
            )

        if criteria.excluded_tags:
            parts.append(
                'Bahan atau rasa yang dihindari: '
                + ', '.join(tag_label(tag) for tag in sorted(criteria.excluded_tags))
                + '.'
            )

        if criteria.budget:
            parts.append('Batas harga minimum per menu: ' + criteria.budget.description() + '.')
        elif criteria.max_price is not None:
            parts.append(
                'Batas harga minimum per menu: maksimal '
                + BudgetConstraint.rupiah(Decimal(criteria.max_price))
                + '.'
            )
        else:
            parts.append('Tidak ada batas harga per menu yang kamu tentukan pada pencarian aktif.')

        if criteria.soft_target is not None:
            parts.append(
                'Perkiraan harga mendekati '
                + BudgetConstraint.rupiah(criteria.soft_target)
                + ', bukan batas tegas.'
            )

        overall = graph['overall']

        if 'total_budget' in overall:
            parts.append(
                'Budget total rencana: '
                + BudgetConstraint.rupiah(Decimal(overall['total_budget']))
                + '.'
            )

        if 'per_person_budget' in overall:
            parts.append(
                'Budget per orang: '
                + BudgetConstraint.rupiah(Decimal(overall['per_person_budget']))
                + '.'
            )

        if 'person_count' in overall:
            parts.append('Jumlah orang: ' + str(overall['person_count']) + '.')

        if overall.get('category_budgets'):
            parts.append(
                'Alokasi kategori: '
                + ', '.join(
                    category + ' ' + BudgetConstraint.rupiah(Decimal(amount))
                    for category, amount in sorted(overall['category_budgets'].items())
                )
                + '.'
            )

        if graph['plan']['entries']:
            names, prices = [], []

            for entry in graph['plan']['entries']:
                item = (
                    MenuItem.objects.filter(pk=entry['menu_id']).select_related('category').first()
                )
                price = self._minimum_payable(item) if item is not None else None
                names.append(
                    str(entry['quantity'])
                    + ' × '
                    + (item.name if item else 'menu yang tidak tersedia')
                    + (' (belum tersedia)' if item is not None and price is None else '')
                )
                prices.append(price * entry['quantity'] if price is not None else None)

            parts.append('Rencana sementara: ' + ', '.join(names) + '.')

            if all(price is not None for price in prices):
                parts.append(
                    'Minimum harga saat ini '
                    + BudgetConstraint.rupiah(sum(prices, Decimal(0)))
                    + '; harga final bergantung pada varian dan tambahan. Ini belum masuk keranjang.'
                )
            else:
                parts.append(
                    'Harga minimum rencana belum dapat dipastikan; periksa pilihan yang tidak tersedia.'
                )

        if graph['plan']['unresolved_roles']:
            parts.append(
                'Kategori yang belum dipilih: ' + ', '.join(graph['plan']['unresolved_roles']) + '.'
            )

        state = self._session_state.load_state().get('state', 'COLLECTING_PREFERENCES')

        return {
            'message': '\n'.join(parts),
            'state': state,
            'preferences': self._response_preferences(self._preferences(), state),
            'recommendations': [],
            'quick_replies': [],
            'active_search': criteria.to_dict(),
        }

    def _prepare_context(self, message: str, action: str | None) -> bool:
        """Stage a semantic transition inside the existing atomic reply draft.

        Return True only for a restored context. Any validation conflict leaves
        its business projection intact; archived constraints are never global.
        """
        self._context_block, self._planned_entries = None, None
        text = normalize_text(message)
        self._session_state.expire_dialog(touch=False)
        data = self._session_state.contexts()
        self._context_action = 'CONTINUE_CONTEXT'

        if action == 'reset' or text in self.RESET_PHRASES:
            self._context_action = 'NEW_REQUEST'

            return False

        if not getattr(settings, 'CHATBOT_CONTEXT_SWITCHING_ENABLED', True):
            self._context_action = 'CLARIFY'
            self._context_block = 'Percakapan sedang dalam pemeliharaan. Pilihan dan batasan sebelumnya tetap tersimpan; coba lagi nanti.'

            return False

        if EntityResolver.is_past_consumption(text):
            self._context_action = 'CLARIFY'

            return False

        if data['active']['legacy_unresolved']:
            only_previous = re.search(
                r'\bhanya\s+(?:(?:untuk|pada)\s+)?(?:pilihan|menu|makanan|minuman)\s+(?:tadi|itu|sebelumnya)\b',
                text,
            )
            all_searches = re.search(r'\b(?:semua|seluruh)\s+(?:pilihan|menu|pencarian)\b', text)

            if only_previous or all_searches:
                if all_searches:
                    data['safety']['excluded_tags'] = sorted(
                        self._session_state.global_exclusions()
                        | self._search_constraints().excluded_tags
                    )

                data['active']['legacy_unresolved'] = False
                self._context_action = 'CORRECT_PREVIOUS'
                self._context_block = 'Cakupan bahan atau rasa yang dihindari sudah dicatat. Sekarang ingin mencari menu apa?'

                return False

        if self._revise_active_preferences(text):
            return False

        extracted = self.tag_extractor.extract(text)
        budget = self.tag_extractor.price_parser.parse(text)
        entity = self._entity_resolver.resolve(text)

        if entity is not None and entity.domain_status == 'GENERAL_CONVERSATION':
            self._context_action = 'CLARIFY'

            return False

        match = (
            self.recommender.get_available_match(entity.menu_ids[0])
            if entity is not None
            and entity.domain_status == 'IN_CATALOG'
            and len(entity.menu_ids) == 1
            else None
        )

        if not re.search(
            r'\b(?:alergi|allergy|allergic|alergen)\b', text
        ) and self._apply_plan_delta(match, budget):
            return False

        if self._plan_delta.implicit_total is not None and match is not None:
            budget = BudgetRequest(
                'total',
                scope='PLAN_TOTAL',
                amount=self._plan_delta.implicit_total,
                requested_categories=(match.item.category.name,),
            )

        category = match.item.category.name if match else extracted.category

        if category is None and 'drink' in extracted.tags:
            category = 'Minuman'

        if category is None and extracted.tags & self.FOOD_TAGS:
            category = 'Camilan' if 'snack' in extracted.tags else 'Makanan'

        previous_category = data['active']['category'] or self._search_constraints().category
        previous_search = self._search_constraints()
        has_active = bool(
            previous_category
            or self._session_state.get_focus() is not None
            or previous_search.required_tags
            or previous_search.budget is not None
            or previous_search.max_price is not None
            or previous_search.soft_target is not None
            or data['overall']
        )

        if budget.scope_ambiguous and not (
            previous_category
            or self._session_state.get_focus() is not None
            or previous_search.required_tags
            or previous_search.budget is not None
            or previous_search.max_price is not None
            or previous_search.soft_target is not None
        ):
            self._context_action = 'CLARIFY'
            self._session_state.set_pending_budget(budget.constraint.maximum)
            self._context_block = (
                'Budget '
                + BudgetConstraint.rupiah(budget.constraint.maximum)
                + ' ini untuk total pesanan atau maksimal per menu?'
            )

            return False

        if budget.kind != 'none' or category is not None or match is not None:
            self._session_state.clear_pending_budget()

        operation, reference = self.interpreter.context_operation(
            text,
            category=category,
            previous_category=previous_category,
            has_active=has_active,
            has_target=match is not None,
            plan_active=bool(data['overall']),
        )
        self._context_action = operation

        if budget.clarification and budget.scope == 'CURRENT_SEARCH':
            self._context_action = 'CLARIFY'

            return False

        if entity is not None and entity.domain_status == 'AMBIGUOUS_CATALOG':
            self._context_action = 'CLARIFY'

            return False

        if operation == 'REFER_TO_PREVIOUS' and match is not None:
            # A named item reference must belong to this session's recent choices.
            owned = set(self._session_state.get_last_recommendation_ids())
            owned.update(entry['menu_id'] for entry in data['plan']['entries'])

            if self._session_state.get_focus() is not None:
                owned.add(self._session_state.get_focus())

            restored_item = False

            if match.item.pk not in owned or category != previous_category:
                restored_item = self._session_state.restore_context(None, menu_id=match.item.pk)

            if restored_item:
                previous_category = data['active']['category']
            elif match.item.pk not in owned and (
                category != previous_category
                or match.item.pk not in self._session_state.get_candidates()
            ):
                self._context_block = 'Aku belum menemukan menu itu di pilihan sebelumnya. Sebutkan nama menu untuk pencarian baru, ya.'
                self._context_action = 'CLARIFY'

                return False
            # Only explicit references restore this owned item's frame. A bare name
            # remains a new search and must not reactivate an old category budget.
        elif operation == 'REFER_TO_PREVIOUS':
            if entity is not None and entity.domain_status == 'IN_CATALOG':
                # A known but unavailable target must not restore unrelated cards.
                self._context_action = 'CLARIFY'
                self._context_block = 'Menu yang kamu maksud belum tersedia untuk dipilih saat ini. Pilihan sebelumnya tetap tersimpan.'

                return False

            if not self._session_state.restore_context(reference):
                self._context_block = 'Aku belum bisa menentukan pilihan sebelumnya yang kamu maksud. Sebutkan kategori atau nama menunya, ya.'
                self._context_action = 'CLARIFY'

                return False

            return True

        if re.search(r'\b(?:alergi|allergy|allergic|alergen)\b', text):
            ingredients = self.tag_extractor.extract_allergy_tags(text)
            data['safety']['excluded_tags'] = sorted(
                set(data['safety']['excluded_tags']) | ingredients
            )
            data['safety']['verification_required'] = True
            self._context_action = 'CLARIFY'

            return False

        if extracted.excluded_tags and re.search(
            r'\b(?:semua|selalu|apa pun|apapun|seluruh)\b', text
        ):
            data['safety']['excluded_tags'] = sorted(
                set(data['safety']['excluded_tags']) | extracted.excluded_tags
            )

        if (
            data['overall']
            and budget.scope == 'CURRENT_SEARCH'
            and budget.constraint is not None
            and category is None
            and match is None
            and operation == 'CORRECT_PREVIOUS'
        ):
            if {'total_budget', 'per_person_budget'} <= set(data['overall']):
                self._context_action = 'CLARIFY'
                self._context_block = 'Budget mana yang ingin diubah: total atau per orang? Sebutkan cakupannya agar batas lain tetap berlaku.'

                return False

            amount = budget.constraint.maximum

            if amount is None or budget.constraint.minimum is not None:
                self._context_action = 'CLARIFY'
                self._context_block = 'Sebutkan satu batas budget total yang baru agar rencana tidak berubah secara keliru.'

                return False

            key = 'per_person_budget' if 'per_person_budget' in data['overall'] else 'total_budget'
            limit = (
                amount * data['overall'].get('person_count', 1)
                if key == 'per_person_budget'
                else amount
            )
            costs = []

            for entry in data['plan']['entries']:
                selected = self.recommender.get_available_match(entry['menu_id'])
                cost = self._minimum_payable(selected.item) if selected is not None else None

                if cost is None:
                    break

                costs.append(cost * entry['quantity'])

            if len(costs) != len(data['plan']['entries']) or sum(costs, Decimal(0)) > limit:
                self._context_action = 'CLARIFY'
                self._context_block = 'Rencana sebelumnya belum memenuhi budget total baru. Pilih item yang ingin diganti atau sebutkan anggaran total lain.'

                return False

            data['overall'][key] = str(amount)
            self._plan_changed = True
            self._context_block = (
                'Budget '
                + ('per orang ' if key == 'per_person_budget' else 'total ')
                + BudgetConstraint.rupiah(amount)
                + ' sudah diperbarui. Pilihan rencana sebelumnya tetap tersimpan; ingin mengganti atau menambahkan menu apa?'
            )

            return False

        if budget.scope != 'CURRENT_SEARCH' and budget.amount is not None:
            existing = bool(data['overall'])

            if not existing:
                self._session_state.archive_context(None)
                self._session_state.commit_plan([])

            data['active']['kind'] = 'PLAN'
            key = 'per_person_budget' if budget.scope == 'PER_PERSON' else 'total_budget'
            data['overall'].update(
                {
                    key: str(budget.amount),
                    'explicitly_declared': True,
                    'plan_id': data['plan']['id'],
                }
            )
            roles = list(
                dict.fromkeys(
                    data['overall'].get('requested_categories', [])
                    + list(budget.requested_categories)
                )
            )
            data['overall']['requested_categories'] = roles

            if budget.person_count is not None:
                data['overall']['person_count'] = budget.person_count

            chosen = set(
                MenuItem.objects.filter(
                    pk__in=[entry['menu_id'] for entry in data['plan']['entries']]
                ).values_list('category__name', flat=True)
            )
            data['plan']['unresolved_roles'] = [role for role in roles if role not in chosen]
            self._plan_changed = True
            self._context_action = 'NEW_REQUEST'

            if match is None:
                count = (
                    f" untuk {budget.person_count} orang" if budget.person_count is not None else ''
                )
                label = 'per orang' if budget.scope == 'PER_PERSON' else 'total'
                people = data['overall'].get('person_count')
                mode = data['plan'].get('serving_mode', 'unspecified')
                question = (
                    'Berapa orang yang akan makan?'
                    if budget.scope == 'PER_PERSON' and people is None
                    else (
                        'Ingin porsi masing-masing atau makanan untuk berbagi?'
                        if people is not None and mode == 'unspecified'
                        else 'Menu makanan atau minuman apa yang ingin kamu pilih?'
                    )
                )
                self._context_block = f"Budget {label} {BudgetConstraint.rupiah(budget.amount)}{count} sudah dicatat. {question} Harga varian wajib dan tambahan tetap perlu diperhitungkan."

                return False

        if match is not None:
            cost = self._minimum_payable(match.item)

            if cost is None or (
                budget.constraint is not None and not budget.constraint.allows(cost)
            ):
                self._context_action = 'CLARIFY'

                return False

            tags = {tag.name for tag in match.item.tags.all()}

            if tags & self._session_state.global_exclusions():
                self._context_block = 'Menu itu memiliki tag bahan yang kamu hindari. Pilih menu lain dan konfirmasikan bahan serta risiko kontak silang kepada staf.'
                self._context_action = 'CLARIFY'

                return False

            self._planned_entries = self._plan_selection(match.item, operation)

            if self._context_block:
                self._context_action = 'CLARIFY'

                return False

        if entity is not None and entity.domain_status == 'IN_CATALOG' and match is None:
            self._context_action = 'CLARIFY'

            return False

        if operation == 'ADD_TO_CONTEXT' and match is None and category is not None:
            focused = self._session_state.get_focus()

            if focused is not None and not data['plan']['entries']:
                data['plan']['entries'] = [
                    {'context_id': data['active']['id'], 'menu_id': focused, 'quantity': 1}
                ]

            role_filled = MenuItem.objects.filter(
                pk__in=[entry['menu_id'] for entry in data['plan']['entries']],
                category__name=category,
            ).exists()

            if not role_filled and category not in data['plan']['unresolved_roles']:
                data['plan']['unresolved_roles'] = (data['plan']['unresolved_roles'] + [category])[
                    -8:
                ]

        fresh = operation in {'SWITCH_CONTEXT', 'NEW_REQUEST'} or (
            operation in {'ADD_TO_CONTEXT', 'CORRECT_PREVIOUS', 'REFER_TO_PREVIOUS'}
            and category is not None
            and category != previous_category
        )

        if fresh and has_active and (data['active']['kind'] != 'PLAN' or bool(previous_category)):
            if data['active']['legacy_unresolved'] and self._search_constraints().excluded_tags:
                self._context_block = 'Pilihan sebelumnya memiliki bahan atau rasa yang dihindari. Batasan itu berlaku juga untuk pencarian baru ini, atau hanya untuk pilihan tadi?'
                self._context_action = 'CLARIFY'

                return False

            self._session_state.archive_context(category, item=match is not None)

            # A linked comparison reuses money bounds only. The drink's tags,
            # item focus and category must not become food requirements.
            if (
                budget.kind == 'none'
                and (previous_search.budget is not None or previous_search.max_price is not None)
                and re.match(
                    r'^(?:kalau(?!\s+(?:gitu|begitu)\b)|bagaimana dengan|gimana dengan|gimana kalau|bagaimana kalau)\b',
                    text,
                )
                and operation == 'SWITCH_CONTEXT'
            ):
                current = self._search_constraints()
                self._session_state.save_search(
                    SearchConstraints(
                        current.required_tags,
                        current.excluded_tags,
                        category,
                        previous_search.max_price,
                        current.moods,
                        budget=previous_search.budget,
                    )
                )

            if (
                not data['overall']
                and operation == 'NEW_REQUEST'
                and re.search(r'\bpermintaan baru\b', text)
            ):
                self._session_state.commit_plan([])

        if (
            match is not None
            and match.item.pk != self._session_state.get_focus()
            and data['active']['item_excluded_tags']
        ):
            item_exclusions = set(data['active']['item_excluded_tags'])
            search = self._session_state.load_constraints()
            self._session_state.save_search(
                SearchConstraints(
                    search.required_tags,
                    search.excluded_tags - item_exclusions,
                    search.category,
                    search.max_price,
                    search.moods,
                    budget=search.budget,
                    soft_target=search.soft_target,
                )
            )
            prefs = self._session_state.load_preferences()
            prefs.excluded_tags.difference_update(item_exclusions)
            self._session_state.save_preferences(prefs, 'RECOMMENDING')
            data['active']['item_excluded_tags'] = []

        if extracted.excluded_tags and re.search(
            r'\b(?:untuk|pada)\s+(?:makanan|menu|item|pilihan)\s+(?:ini|itu)\b', text
        ):
            data['active']['item_excluded_tags'] = sorted(extracted.excluded_tags)

        if category is not None:
            data['active']['category'] = category

        if not has_active and match is not None and data['active']['kind'] != 'PLAN':
            data['active']['kind'] = 'ITEM'

        return False

    def _combination_response(self, message: str) -> ChatbotResponse:
        """Build a proposal in this turn's draft; persistence stays with reply/CAS."""
        self._session_state.expire_dialog(touch=False)
        data = self._session_state.contexts()
        delta = self._plan_delta

        has_existing_plan = bool(data['overall'] or data['plan']['entries'])

        def reject(reason: str) -> ChatbotResponse:
            self._plan_error = True
            self._context_action, self._context_block = 'CLARIFY', reason

            return self._budget_clarification(self._preferences(), reason)

        if delta.clarification or EntityResolver.is_past_consumption(message):
            return reject(delta.clarification or 'Sebutkan kombinasi yang ingin dicari sekarang.')

        if re.search(
            r'\b(?:jangan|bukan|tanpa|tidak mau|ga mau|gak mau)\s+(?:pakai\s+)?kombinasi\b',
            normalize_text(message),
        ):
            return reject('Sebutkan kategori atau nama menu yang ingin dicari tanpa kombinasi.')

        budget = self.tag_extractor.price_parser.parse(message)

        if (
            budget.clarification
            and not (budget.scope != 'CURRENT_SEARCH' and budget.amount is not None)
            and not delta.category_budgets
        ):
            return reject(budget.clarification)

        if budget.soft_target is not None:
            return reject(
                'Perkiraan harga tidak menjadi batas total. Sebutkan budget total kombinasi atau cari harga sekitar itu per menu.'
            )

        try:
            for amount in [
                *delta.category_budgets.values(),
                delta.total_budget,
                delta.per_person_budget,
            ]:
                if amount is not None:
                    BudgetConstraint(maximum=Decimal(amount))
        except (ValueError, ArithmeticError):
            return reject('Sebutkan alokasi antara Rp0 dan Rp1.000.000 untuk setiap cakupan.')

        roles = list(
            delta.requested_roles
            or data['overall'].get('requested_categories', [])
            or data['plan']['unresolved_roles']
        )

        if not roles:
            return reject(
                'Kategori apa saja untuk kombinasi ini, dan berapa porsi tiap kategorinya?'
            )

        selected = None
        preference_text = message

        if delta.target_role is not None and delta.entity_text is not None:
            entity = self._entity_resolver.resolve(delta.entity_text)

            if entity is None or entity.domain_status != 'IN_CATALOG' or len(entity.menu_ids) != 1:
                return reject(
                    'Menu untuk '
                    + delta.target_role
                    + ' belum jelas. Sebutkan satu nama menu yang spesifik.'
                )

            selected = self.recommender.get_available_match(entity.menu_ids[0])

            if selected is None or selected.item.category.name != delta.target_role:
                return reject(
                    'Menu tersebut belum tersedia untuk kategori '
                    + delta.target_role
                    + '. Pilih menu lain dalam kategori itu.'
                )

            modifiers = self.tag_extractor.extract(entity.modifiers or '')

            if (
                modifiers.tags
                or modifiers.excluded_tags
                or modifiers.soft_excluded_tags
                or self.tag_extractor.price_parser.parse('menu ' + (entity.modifiers or '')).kind
                != 'none'
            ):
                return reject(
                    'Untuk pilihan kategori itu, sebutkan nama menunya dahulu dan ubah filter dalam pesan berikutnya.'
                )

            # The selected menu's words are identity, not tastes for every role.
            preference_text = self.tag_extractor.price_parser.normalize_money_input(
                message
            ).rpartition(delta.entity_text.removeprefix('mau '))[0]

        extracted = self.tag_extractor.extract(preference_text)
        new_required = extracted.tags - {'drink', 'snack', 'filling', 'sharing'}

        if new_required and len(roles) > 1:
            return reject(
                'Selera atau bahan ini untuk kategori yang mana? Sebutkan kategorinya dahulu agar tidak diterapkan ke makanan dan minuman sekaligus.'
            )

        if len(roles) > CombinationPlanner.MAX_ROLES:
            return reject(
                'Pencarian kombinasi terbatas pada tiga kategori. Pilih kategori yang ingin dicari bersama.'
            )

        if len(set(data['overall'].get('requested_categories', [])) | set(roles)) > 8:
            return reject(
                'Rencana maksimal memiliki delapan kategori. Batalkan kategori yang tidak diperlukan dahulu.'
            )

        if delta.cancel_role or delta.quantity is not None:
            return reject(
                'Untuk kombinasi, sebutkan jumlah per kategori; untuk satu menu, sebutkan nama dan jumlahnya tanpa kata kombinasi.'
            )

        overall = data['overall']
        amounts = [mention for mention in budget.numeric_roles if mention.role == 'MONEY']

        if delta.category_budgets:
            overall['category_budgets'] = {
                **overall.get('category_budgets', {}),
                **delta.category_budgets,
            }

            if (
                delta.implicit_total is not None
                and 'total_budget' not in overall
                and 'per_person_budget' not in overall
            ):
                overall['total_budget'] = str(delta.implicit_total)

        if delta.total_budget is not None:
            overall['total_budget'] = str(delta.total_budget)

        if delta.per_person_budget is not None:
            overall['per_person_budget'] = str(delta.per_person_budget)

        if budget.scope != 'CURRENT_SEARCH' and budget.amount is not None:
            overall['per_person_budget' if budget.scope == 'PER_PERSON' else 'total_budget'] = str(
                budget.amount
            )
        elif (
            len(amounts) == 1
            and not delta.category_budgets
            and not re.search(
                r'\b(?:per (?:menu|item|porsi)|maksimal|minimal|di atas|di bawah|lebih dari|kurang dari)\b',
                normalize_text(message),
            )
        ):
            overall['total_budget'] = str(amounts[0].value)
        elif amounts and not delta.category_budgets:
            return reject('Sebutkan budget total atau alokasi setiap kategori untuk kombinasi ini.')

        if overall:
            overall.update(explicitly_declared=True, plan_id=data['plan']['id'])
            overall['requested_categories'] = list(
                dict.fromkeys(overall.get('requested_categories', []) + roles)
            )

        if budget.person_count is not None or delta.person_count is not None:
            if not overall:
                return reject('Sebutkan budget total atau per orang untuk rencana kelompok ini.')

            overall['person_count'] = budget.person_count or delta.person_count

        people = overall.get('person_count')
        mode = delta.serving_mode or data['plan'].get('serving_mode', 'unspecified')

        if people and mode == 'unspecified':
            return reject(
                'Untuk rencana kelompok ini, ingin satu porsi tiap kategori per orang atau berbagi? Sebutkan masing-masing atau jumlah porsi tiap kategori.'
            )

        if 'per_person_budget' in overall and not people:
            return reject('Berapa orang untuk budget per orang ini?')

        quantities = {
            role: delta.role_quantities.get(
                role,
                data['plan']
                .get('role_quantities', {})
                .get(role, people if mode == 'individual' and people else 1),
            )
            for role in roles
        }

        if mode == 'shared' and not all(
            role in delta.role_quantities or role in data['plan'].get('role_quantities', {})
            for role in roles
        ):
            return reject(
                'Untuk berbagi, berapa porsi makanan dan jumlah minuman yang ingin dicari?'
            )

        if sum(quantities.values()) > CombinationPlanner.MAX_SLOTS:
            return reject(
                'Pencarian kombinasi otomatis maksimal delapan porsi. Perkecil jumlah; pilihan satu menu dengan jumlah eksplisit tetap bisa dihitung langsung.'
            )

        if len(set(data['plan'].get('role_quantities', {})) | set(roles)) > 8:
            return reject(
                'Rencana maksimal memiliki delapan kategori. Batalkan kategori yang tidak diperlukan dahulu.'
            )

        if mode != 'unspecified':
            data['plan']['serving_mode'] = mode

        entries = deepcopy(data['plan']['entries'])
        categories = dict(
            MenuItem.objects.filter(pk__in=[entry['menu_id'] for entry in entries]).values_list(
                'pk', 'category__name'
            )
        )
        retained = [entry for entry in entries if categories.get(entry['menu_id']) not in roles]
        retained_total, error = self._plan_facts(retained)

        if error:
            return reject(error)

        frames = [data['active'], *reversed(data['previous'])]
        constraints_by_role = {}
        pools = {}

        for role in roles:
            frame = next((frame for frame in frames if frame['category'] == role), None)

            if frame is None:
                previous_entry = next(
                    (entry for entry in entries if categories.get(entry['menu_id']) == role), None
                )
                frame = (
                    data['plan'].get('scopes', {}).get(str(previous_entry['context_id']))
                    if previous_entry
                    else None
                )

            original = (
                (
                    self._search_constraints()
                    if frame is data['active']
                    else SearchConstraints.from_dict(frame['constraints'])
                )
                if frame
                else SearchConstraints()
            )
            excluded = (
                original.excluded_tags - set(frame['item_excluded_tags'])
                if frame
                else original.excluded_tags
            )
            criteria = SearchConstraints(
                original.required_tags | frozenset(new_required),
                frozenset(excluded)
                | frozenset(extracted.excluded_tags)
                | self._session_state.global_exclusions(),
                role,
                original.max_price,
                original.moods,
                budget=original.budget,
                soft_target=original.soft_target,
            )
            constraints_by_role[role] = criteria
            pinned = selected is not None and role == delta.target_role
            # Explicit identity is validated by rank before reducing its pool to one.
            limit = MenuItem.objects.count() if pinned else CombinationPlanner.MAX_CANDIDATES + 1
            matches = self.recommender.rank(
                Preferences(),
                limit=limit,
                exclude_ids=self._session_state.get_explicit_rejections(),
                constraints=criteria,
                include_unscored=True,
            )

            if pinned:
                matches = [match for match in matches if match.item.pk == selected.item.pk]

            pools[role] = [
                CombinationCandidate(match.item.pk, cost)
                for match in matches
                if (cost := self._minimum_payable(match.item)) is not None
            ]

        limits = [Decimal(overall['total_budget'])] if 'total_budget' in overall else []
        per_person = (
            Decimal(overall['per_person_budget']) if 'per_person_budget' in overall else None
        )

        if per_person is not None:
            limits.append(per_person * people)

        maximum = min(limits) - retained_total if limits else None
        remaining_person = per_person

        if per_person is not None and mode == 'individual':
            remaining_person -= sum(
                (
                    self._minimum_payable(
                        self.recommender.get_available_match(entry['menu_id']).item
                    )
                    * ((entry['quantity'] + people - 1) // people)
                    for entry in retained
                ),
                Decimal(0),
            )

        proposal = CombinationPlanner().propose(
            pools,
            quantities,
            maximum=maximum,
            category_limits={
                role: Decimal(amount)
                for role, amount in overall.get('category_budgets', {}).items()
            },
            people=people,
            per_person=remaining_person,
            individual=mode == 'individual',
        )

        if not proposal.quantities:
            if proposal.limited:
                return reject(
                    'Pencarian kombinasi mencapai batas kandidat atau langkah. Belum ditemukan kombinasi dalam pencarian terbatas ini; persempit kategori atau pilih nama menu.'
                )

            if (
                not has_existing_plan
                and selected is None
                and not delta.category_budgets
                and not re.search(
                    r'\b(?:kombinasi|susun paket|buat|carikan|cari)\b', normalize_text(message)
                )
            ):
                # A valid first budget declaration can remain pending without selecting items.
                data['plan']['unresolved_roles'] = roles
                data['plan']['role_quantities'] = quantities
                self._context_action = 'CLARIFY'

                return self._budget_clarification(
                    self._preferences(),
                    'Belum ditemukan kombinasi yang memenuhi budget ini. Batas rencana tetap dicatat; belum ada menu yang dipilih. Mau mengubah budget atau kategorinya?',
                )

            return reject(
                'Belum ditemukan kombinasi pada pilihan yang memenuhi jumlah, budget dan batas saat ini. Ubah pilihan atau jumlah secara eksplisit; alokasi porsi campuran per orang belum dapat dipastikan.'
            )

        if len(retained) + len(proposal.quantities) > CombinationPlanner.MAX_ENTRIES:
            return reject(
                'Rencana maksimal delapan item berbeda. Pilih kategori yang ingin diganti dahulu.'
            )

        # Preserve existing role scopes, including frames about to be archived.
        self._session_state.commit_plan(entries)
        self._session_state.archive_context(None)
        data['active']['kind'] = 'PLAN'
        scopes = {}

        for role, pool in pools.items():
            owner = data['next_id']
            data['next_id'] += 1
            identifiers = {candidate.menu_id for candidate in pool}
            chosen = {key: qty for key, qty in proposal.quantities.items() if key in identifiers}
            scopes[str(owner)] = {
                'constraints': constraints_by_role[role].to_dict(),
                'focused_item_id': None,
                'item_excluded_tags': [],
            }
            retained.extend(
                {'context_id': owner, 'menu_id': identifier, 'quantity': quantity}
                for identifier, quantity in chosen.items()
            )

        self._session_state.commit_plan(retained, scopes=scopes)
        data['plan']['role_quantities'] = {**data['plan'].get('role_quantities', {}), **quantities}
        data['plan']['unresolved_roles'] = [
            role for role in data['plan']['unresolved_roles'] if role not in roles
        ]
        self._context_action, self._response_purpose = 'NEW_REQUEST', 'recommendation'
        self._response_intent = ConversationIntent.RECOMMEND
        self._combination_limited = proposal.limited
        self._combination_pending = True

        return {
            'message': '',
            'state': 'RECOMMENDING',
            'preferences': self._preferences().to_dict(),
            'recommendations': [],
            'quick_replies': [],
        }

    def _finish_combination(self, result: ChatbotResponse) -> bool:
        data = self._session_state.contexts()
        entries = data['plan']['entries']
        total, error = self._plan_facts(entries)

        if error:
            self._context_block = error

            return False

        matches = [self.recommender.get_available_match(entry['menu_id']) for entry in entries]
        # _plan_facts re-reads all required variants and owned criteria. Build
        # wording from this final check, never the solver's earlier quoted total.
        result['recommendations'] = matches
        result['message'] = (
            'Ini satu kombinasi, dipilih bersama: '
            + ', '.join(
                f"{entry['quantity']} × {match.item.name}" for entry, match in zip(entries, matches)
            )
            + '.'
        )
        result['message'] += (
            '\nMinimal harga rencana sementara '
            + BudgetConstraint.rupiah(total)
            + '. Termasuk varian wajib termurah; harga final bergantung pada pilihan varian dan tambahan. Ini belum masuk keranjang.'
        )

        if self._combination_limited:
            result[
                'message'
            ] += '\nKombinasi ini ditemukan dalam pencarian kandidat terbatas; bukan satu-satunya pilihan atau jaminan paling optimal.'

        if data['plan']['unresolved_roles']:
            result['message'] += (
                '\nKategori yang masih perlu dipilih: '
                + ', '.join(data['plan']['unresolved_roles'])
                + '.'
            )

        if data['safety']['verification_required']:
            result[
                'message'
            ] += '\nPastikan bahan dan risiko kontak silang kepada staf. Informasi menu tidak menjamin keamanan alergi.'

        if 'per_person_budget' in data['overall'] and (
            data['plan'].get('serving_mode') != 'individual'
            or any(entry['quantity'] % data['overall']['person_count'] for entry in entries)
        ):
            result['message'] += '\nPembagian porsi per orang belum dipastikan.'

        result['combination'] = {
            'entries': deepcopy(entries),
            'minimum_total': str(total),
            'price_basis': 'minimum_payable',
            'final_price_confirmed': False,
            'limited_search': self._combination_limited,
        }
        ids = [entry['menu_id'] for entry in entries]
        self._session_state.record_recommendations(ids, shown_ids=ids)
        self._save(self._preferences(), 'RECOMMENDING')
        result['preferences'] = self._response_preferences(self._preferences(), 'RECOMMENDING')
        self._session_state.finish_context(self._context_action, self._response_intent)

        return True

    def _finish_context(self, result: ChatbotResponse) -> bool:
        if self._plan_error:
            self._plan_error = False

            return False

        if self._combination_pending:
            return self._finish_combination(result)

        data = self._session_state.contexts()

        if (result['recommendations'] or self._plan_changed) and (
            data['overall'] or data['plan']['entries'] or self._planned_entries is not None
        ):
            if self._planned_entries is not None:
                for entry in self._planned_entries:
                    if entry['menu_id'] == self._session_state.get_focus():
                        entry['context_id'] = data['active']['id']

                _, error = self._plan_facts(self._planned_entries)

                if error:
                    self._context_block = error

                    return False

            if self._plan_changed and self._planned_entries is None:
                _, error = self._plan_facts(data['plan']['entries'])

                if error:
                    self._context_block = error

                    return False

            fresh_pool = self.recommender.rank(
                self._preferences(),
                limit=ConversationSession.MAX_HISTORY,
                constraints=self._search_constraints(),
                include_unscored=True,
            )
            fresh = {match.item.pk: match for match in fresh_pool}
            selected_ids = [match.item.pk for match in result['recommendations']]

            if any(identifier not in fresh for identifier in selected_ids):
                self._context_block = 'Data menu berubah sebelum pilihan selesai diperiksa. Pilihan sebelumnya tetap tersimpan; coba pilih menu kembali, ya.'

                return False

            result['recommendations'] = [fresh[identifier] for identifier in selected_ids]
            result['explanations'] = {
                match.item.pk: self.explanation_service.fallback(match)
                for match in result['recommendations']
            }

        if self._response_purpose == 'clarification' and not self._context_block:
            self._context_action = 'CLARIFY'

        if data['overall'] and result['recommendations'] and self._planned_entries is None:
            eligible = self._eligible_for_plan(result['recommendations'])

            if len(eligible) != len(result['recommendations']):
                result['recommendations'] = eligible
                ids = [match.item.pk for match in eligible]
                self._session_state.record_recommendations(ids, shown_ids=ids)

                if not eligible:
                    result.update(
                        self._budget_clarification(
                            self._preferences(),
                            'Belum ada pilihan yang memenuhi budget total dan rencana saat ini. Pilih pengganti atau ubah anggaran totalnya.',
                        )
                    )
                    self._context_action = 'CLARIFY'
                    self._planned_entries = None

        if self._planned_entries is not None and (
            result['recommendations'] or self._plan_update_only
        ):
            for entry in self._planned_entries:
                if entry['menu_id'] == self._session_state.get_focus():
                    entry['context_id'] = data['active']['id']

            self._session_state.commit_plan(self._planned_entries)
            chosen_categories = {
                item.category.name
                for item in MenuItem.objects.filter(
                    pk__in=[entry['menu_id'] for entry in self._planned_entries]
                ).select_related('category')
            }
            data['plan']['unresolved_roles'] = [
                role for role in data['plan']['unresolved_roles'] if role not in chosen_categories
            ]
            self._plan_changed = True

        if self._plan_changed and data['plan']['entries']:
            self._session_state.commit_plan(data['plan']['entries'])
            missing = data['plan']['unresolved_roles']

            if missing:
                result['message'] += (
                    '\nKategori yang masih perlu dipilih: ' + ', '.join(missing) + '.'
                )

        if data['plan']['entries'] and 'per_person_budget' in data['overall']:
            count = data['overall'].get('person_count')
            uniform = bool(count) and all(
                entry['quantity'] % count == 0 for entry in data['plan']['entries']
            )

            if data['plan'].get('serving_mode') != 'individual' or not uniform:
                result[
                    'message'
                ] += '\nBudget per orang tetap tercatat; pembagian porsi per orang belum dipastikan. Sebutkan porsi masing-masing atau berbagi.'

        if data['safety']['excluded_tags']:
            search = self._search_constraints()
            self._session_state.save_search(search)
            result['active_search'] = search.to_dict()

        if data['safety']['verification_required'] and result['recommendations']:
            result[
                'message'
            ] += '\nPastikan bahan dan risiko kontak silang kepada staf. Informasi menu tidak menjamin keamanan alergi.'

        if data['overall'] and data['plan']['entries'] and result['recommendations']:
            costs = []

            for entry in data['plan']['entries']:
                match = self.recommender.get_available_match(entry['menu_id'])
                cost = self._minimum_payable(match.item) if match is not None else None

                if cost is None:
                    costs = []
                    break

                costs.append(cost * entry['quantity'])

            if costs:
                result['message'] += (
                    '\nMinimal harga rencana sementara '
                    + BudgetConstraint.rupiah(sum(costs, Decimal(0)))
                    + '. Total final bergantung pada pilihan varian dan tambahan; ini belum masuk keranjang.'
                )

        self._session_state.finish_context(self._context_action, self._response_intent)

        return True

    def _requests_option_selection(self, message: str) -> bool:
        """Recognize a bounded unsupported action, never select or price an option."""
        text = normalize_text(message)

        if EntityResolver.is_past_consumption(text) or re.search(
            r'\b(?:alergi|allergy|allergic|alergen)\b', text
        ):
            return False

        identity = self._entity_resolver.resolve(text)

        if identity is not None and identity.domain_status == 'IN_CATALOG':
            # Remove real menu names/aliases before looking for option words.
            # "Nasi Tambah Telur" is an item, not a request to configure one.
            if identity.modifiers is None:
                return False

            text = identity.modifiers

        names = None
        negative = r'\b(?:jangan|tanpa|bukan|(?:tidak|ga|gak|nggak)(?: mau| ingin| usah| perlu| jadi)?)\s*$'
        explicit = r'^(?:add[- ]?on|tambahan|varian|opsi)\b'

        for clause in re.split(r'[,;.!?]|\b(?:tapi|dan|serta)\b', text):
            clause = clause.strip()
            targets = [(0, clause)] if re.match(explicit, clause) else []
            targets.extend(
                (match.start(), clause[match.end() :].strip())
                for match in re.finditer(
                    r'\b(?:tambah(?:kan)?|pilih|pakai|gunakan|mau|ingin|minta|ganti(?: ke)?|ubah(?: ke)?)\s+',
                    clause,
                )
            )

            for start, target in targets:
                if re.search(negative, clause[:start]) or re.match(
                    r'^(?:tanpa|bukan|jangan|tidak)\b', target
                ):
                    continue

                if re.match(explicit, target):
                    return True

                if names is None:
                    names = {
                        normalize_text(name)
                        for name in AddOn.objects.values_list('name', flat=True)
                    }
                    names.update(
                        normalize_text(name)
                        for name in VariantOption.objects.values_list('name', flat=True)
                        if not self.tag_extractor.extract(name).tags
                    )

                if any(name and re.match(re.escape(name) + r'(?!\w)', target) for name in names):
                    return True

        return False

    def reply(self, message: str, more: bool = False, action: str | None = None) -> ChatbotResponse:
        self._turn_generator.reset()
        self._turn_generator.protect(message)
        self._turn_source_session = self.session
        self.response_plan = None
        self._response_purpose, self._response_intent = 'clarification', None
        self._response_tone = 'friendly'
        self._plan_delta, self._requested_quantity = PlanDelta(), None
        self._plan_changed, self._plan_update_only, self._plan_error = False, False, False
        self._combination_pending, self._combination_limited = False, False
        original_session, original_state, original_responses = (
            self.session,
            self._session_state,
            self._responses,
        )
        draft = original_state.draft()
        self.session = draft
        self._session_state = ConversationSession(draft)
        self._responses = LocalResponseComposer(draft)

        try:
            if not more and not action and self._is_context_summary(message):
                self._response_purpose = 'help'
                self._response_intent = ConversationIntent.HELP
                self._session_state.expire_dialog(touch=False)
                result = self._context_summary()
                self.response_plan = ResponsePlan(
                    'help',
                    [],
                    self._preferences(),
                    intent=ConversationIntent.HELP,
                    constraints=self._search_constraints(),
                    quick_replies=[],
                )

                return result

            amount = self._session_state.pending_budget()
            answer = normalize_text(message).strip(' .!?')

            if (
                amount is not None
                and action not in {'reset', 'more'}
                and answer in {'per menu', 'per item', 'per porsi', 'total', 'total pesanan'}
            ):
                message = (
                    ('budget total ' if answer.startswith('total') else 'budget ')
                    + str(amount)
                    + ' rupiah'
                    + ('' if answer.startswith('total') else ' per menu')
                )
                self._session_state.clear_pending_budget()

            option_request = (
                not more
                and action not in {'reset', 'more'}
                and self._requests_option_selection(message)
            )
            self._plan_delta = (
                PlanDelta() if option_request else self.plan_interpreter.interpret(message)
            )

            if (
                self._plan_delta.entity_text is not None
                and not self._plan_delta.combination_request
            ):
                message = self._plan_delta.entity_text

            self._context_block, self._planned_entries = None, None
            combination = (
                self._plan_delta.combination_request
                and action not in {'reset', 'more'}
                and not re.search(
                    r'\b(?:alergi|allergy|allergic|alergen)\b', normalize_text(message)
                )
            )

            if combination and self._plan_delta.target_role is None:
                identity = self._entity_resolver.resolve(message)

                if (
                    identity is not None
                    and identity.domain_status == 'IN_CATALOG'
                    and identity.modifiers is not None
                    and not any(
                        mention.role == 'MONEY'
                        for mention in self.tag_extractor.price_parser.numeric_roles(
                            identity.modifiers
                        )
                    )
                ):
                    combination = False  # A literal amount inside a menu name is identity.

            price_question = (
                self._named_price_question(message)
                if not more and not action and not combination and not option_request
                else None
            )
            restored = (
                False
                if combination or option_request or price_question is not None
                else self._prepare_context(message, action)
            )

            if price_question is not None:
                result = price_question
            elif option_request:
                self._session_state.expire_dialog()
                self._context_action = 'CLARIFY'
                result = self._budget_clarification(
                    self._preferences(), self._responses.option_boundary()
                )
            elif combination:
                result = self._combination_response(message)
            elif self._context_block:
                result = self._budget_clarification(self._preferences(), self._context_block)
            elif restored:
                self._response_intent = ConversationIntent.RECOMMEND
                result = self._recommend(
                    self._preferences(), message, constraints=self._search_constraints()
                )
            else:
                result = self._reply_turn(message, more, action)

            if not self._finish_context(result):
                # Reject a stale draft atomically, retaining usage and explicit
                # safety declarations. Never commit its new focus or archives.
                rejected = draft
                safety = deepcopy(self._session_state.contexts()['safety'])
                reason = (
                    self._context_block
                    or 'Data rencana berubah. Pilih kembali menu yang diinginkan.'
                )
                draft = original_state.draft()
                self.session = draft
                self._session_state = ConversationSession(draft)
                self._session_state.preserve_usage(rejected)
                self._session_state.expire_dialog()
                previous_safety = self._session_state.contexts()['safety']
                previous_safety['excluded_tags'] = sorted(
                    set(previous_safety['excluded_tags']) | set(safety['excluded_tags'])
                )
                previous_safety['verification_required'] |= safety['verification_required']
                self._responses = LocalResponseComposer(draft)
                self._planned_entries, self._context_action = None, 'CLARIFY'
                self._plan_changed, self._plan_update_only = False, False
                self._combination_pending = False
                self._context_block = reason
                result = self._budget_clarification(self._preferences(), reason)
                self._finish_context(result)

            entries = self._session_state.contexts()['plan']['entries']
            minimum, error = (
                self._plan_facts(entries)
                if entries and self._response_purpose != 'clarification'
                else (None, None)
            )
            self.response_plan = ResponsePlan(
                self._response_purpose,
                result['recommendations'],
                self._preferences(),
                intent=self._response_intent,
                constraints=self._search_constraints(),
                tone=(
                    'clarifying'
                    if self._response_purpose == 'clarification'
                    else self._response_tone
                ),
                required_clarification=(
                    result['message'] if self._response_purpose == 'clarification' else None
                ),
                quick_replies=result['quick_replies'],
                quantities={entry['menu_id']: entry['quantity'] for entry in entries},
                verified_plan_minimum=minimum if error is None else None,
            )
            original_state.commit(draft)

            return result
        except Exception:
            # Provider attempts must remain charged even if a later state step fails.
            original_state.preserve_usage(draft)

            raise
        finally:
            self.session, self._session_state, self._responses = (
                original_session,
                original_state,
                original_responses,
            )
            self._turn_generator.reset()
            self._turn_source_session = None
            self._semantic_query, self._semantic_tags = None, set()
            self._planned_entries, self._context_block = None, None
            self._plan_delta, self._requested_quantity = PlanDelta(), None
            self._plan_changed, self._plan_update_only, self._plan_error = False, False, False

    def _reply_turn(
        self, message: str, more: bool = False, action: str | None = None
    ) -> ChatbotResponse:
        normalized = normalize_text(message)
        self._turn_generator.protect(
            normalized,
            sensitive_context=bool(
                self._session_state.contexts()['safety']['verification_required']
            ),
        )

        if action == "reset" or normalized in self.RESET_PHRASES:
            return self._reply(message, more, action)

        if EntityResolver.is_past_consumption(normalized):
            return self._entity_response(
                EntityResolution('menu sebelumnya', 'GENERAL_CONVERSATION', 'context'),
                self._preferences(),
                ConversationInterpretation(ConversationIntent.UNKNOWN),
            )

        self._session_state.expire_dialog(touch=False)

        if re.search(r"\b(?:alergi|alergen|allergy|allergic)\b", normalized):
            return self._budget_clarification(
                self._preferences(),
                "Informasi tag menu belum cukup untuk memastikan keamanan alergi. "
                "Sebutkan bahan yang perlu dihindari kepada staf agar bahan dan risiko kontak silang bisa dikonfirmasi sebelum memilih menu.",
            )

        context = self.mood_extractor.extract_context(normalized)
        self._session_state.expire_dialog()
        old_explicit_tags = self._preferences().tags - set(
            self.session.get(ConversationSession.INFERRED_KEY, [])
        )
        extracted = self.tag_extractor.extract(normalized)
        explicit_food = bool(
            extracted.tags
            or extracted.excluded_tags
            or extracted.soft_excluded_tags
            or extracted.category
        )
        had_context = bool(self.session.get(ConversationSession.TEMP_CONTEXT_KEY))
        clear = self._session_state.advance_context(context, explicit_food=explicit_food)

        if clear or (self._preferences().moods and not had_context and not context.physical):
            self._clear_temporary_moods()

        self._current_context = context if context.has_context or (clear and had_context) else None

        try:
            legacy_moods = self.mood_extractor.extract(normalized) - {"confused", "low_mood"}
            request_cue = re.search(r"\b(?:ingin|mau|ada|jual|beli|pesan)\b", normalized)
            self._current_entity_text = None

            if context.has_context and request_cue:
                request_text = normalized[request_cue.start() :]
                resolved = self._entity_resolver.resolve(request_text)

                if not explicit_food or (
                    resolved is not None and resolved.domain_status == "IN_CATALOG"
                ):
                    self._current_entity_text = request_text

            budget = self.tag_extractor.price_parser.parse(normalized)
            control = (
                more
                or bool(action)
                or any(phrase in normalized for phrase in self.MORE_PHRASES)
                or re.search(r"\byang (?:pertama|kedua|tadi|terakhir)\b", normalized)
            )

            if (
                context.has_context
                and not explicit_food
                and not legacy_moods
                and not request_cue
                and not control
                and budget.kind == "none"
                and not context.cleared_physical
            ):
                result = self._budget_clarification(
                    self._preferences(),
                    "Kalau ingin mencari makanan atau minuman, aku bisa bantu. Lagi ingin yang seperti apa?",
                )
            else:
                result = self._reply(message, more, action)

            if context.physical and not request_cue:
                inferred = (extracted.tags & {'drink', 'filling', 'quick_meal'}) - old_explicit_tags

                if inferred:
                    self.session[ConversationSession.INFERRED_KEY] = sorted(inferred)

            acknowledgement = self._context_acknowledgement(context)

            if context.has_context and result["message"].startswith(
                ("Hehe, aku belum", "Aku belum yakin", "Boleh kasih sedikit", "Aku masih belum")
            ):
                result["message"] = "Lagi ingin makanan atau minuman seperti apa?"

            if acknowledgement:
                self._response_tone = 'empathetic'
                body = result["message"]

                if (
                    result["recommendations"]
                    and "\n" in body
                    and not result.get("catalog_question")
                ):
                    body = body.split("\n", 1)[1]

                result["message"] = acknowledgement + "\n" + body

            return result
        finally:
            self._current_context = None
            self._current_entity_text = None

    def _reply(
        self, message: str, more: bool = False, action: str | None = None
    ) -> ChatbotResponse:
        normalized = normalize_text(message)
        action = action or ""

        if action == "reset" or normalized in self.RESET_PHRASES:
            self._response_intent = ConversationIntent.RESET
            had_safety = bool(self._session_state.contexts()['safety']['verification_required'])
            self.reset()
            result = self._question()

            if had_safety:
                result[
                    'message'
                ] += '\nPercakapan baru menghapus pilihan sebelumnya. Sampaikan kembali alergi atau bahan yang perlu dihindari kepada staf sebelum memilih menu.'

            return result

        if not normalized:
            preferences = self._preferences()

            return (
                self._greeting_response(preferences)
                if self._has_preferences(preferences)
                else self._question()
            )

        session_state = self._session_state.load_state()
        pending_question = session_state.get(
            "last_question",
            self._session_state.get_last_question(),
        )
        open_followup_answer = normalized in self.OPEN_FOLLOWUP_ANSWERS and pending_question in {
            "meal_type",
            "base",
        }
        confusion = next(
            (phrase for phrase in self.CONFUSION_PHRASES if phrase in normalized), None
        )

        if confusion and not open_followup_answer:
            extracted = self.tag_extractor.extract(normalized)
            moods = self.mood_extractor.extract(normalized)
            meaningful = bool(
                extracted.tags
                or extracted.excluded_tags
                or extracted.soft_excluded_tags
                or extracted.max_price is not None
                or extracted.category
                or extracted.prefer_affordable
                or (moods - {"confused"})
            )

            if not meaningful:
                state = self._session_state.load_state().get("state", "COLLECTING_PREFERENCES")
                preferences = self._preferences()

                if not self._has_preferences(preferences):
                    state = "COLLECTING_PREFERENCES"

                response = self._question(confused=True)

                return {
                    "message": response["message"],
                    "state": state,
                    "preferences": preferences.to_dict(state=state),
                    "recommendations": [],
                    "quick_replies": response["quick_replies"],
                }

        more = more or action == "more" or normalized in self.MORE_PHRASES
        preferences = self._preferences()
        session_state = self._session_state.load_state()
        old_follow_up = session_state.get("follow_up")
        interpretation = self.interpreter.interpret(
            normalized,
            last_question=self._session_state.get_last_question(),
            last_recommendations=self._session_state.get_last_recommendation_ids(),
            last_result_empty=self._session_state.last_result_empty(),
        )
        self._response_intent = interpretation.intent
        budget_request = self.tag_extractor.price_parser.parse(normalized)
        interpretation.context_action = self._context_action
        interpretation.constraint_scope = (
            'PLAN_TOTAL' if self._session_state.contexts()['overall'] else 'CURRENT_SEARCH'
        )

        if budget_request.scope != 'CURRENT_SEARCH':
            budget_request = BudgetRequest()

        if normalized.isdecimal() and pending_question != "budget":
            budget_request = BudgetRequest()

        entity = self._entity_resolver.resolve(self._current_entity_text or normalized)
        named_reference = entity is not None and entity.domain_status in {
            'IN_CATALOG',
            'AMBIGUOUS_CATALOG',
        }

        if entity is not None and entity.domain_status == 'REJECTED_CATALOG':
            interpretation.intent = ConversationIntent.REJECT_RECOMMENDATION
            interpretation.rejected_menu_ids = entity.rejected_menu_ids

        if entity is not None and entity.modifiers is not None:
            modifiers = self.tag_extractor.extract(entity.modifiers)
            interpretation.tags = modifiers.tags
            interpretation.excluded_tags = modifiers.excluded_tags
            interpretation.soft_excluded_tags = modifiers.soft_excluded_tags
            # Numbers inside a verified catalog name are identity, not budget.
            # Keep an explicit food context for plain prices outside that name.
            budget_request = self.tag_extractor.price_parser.parse('menu ' + entity.modifiers)

            if (
                budget_request.scope != 'CURRENT_SEARCH'
                or self._plan_delta.implicit_total is not None
            ):
                budget_request = BudgetRequest()

        if named_reference and entity is not None and entity.domain_status == 'IN_CATALOG':
            interpretation.intent = ConversationIntent.SELECT_RECOMMENDATION
            interpretation.target_menu_id = entity.menu_ids[0]
            interpretation.rejected_menu_ids = entity.rejected_menu_ids

        # A preference revision can refer to a saved choice before cards exist;
        # an ordinal selection still requires actual previous recommendations.
        if (
            interpretation.contextual_reference
            and interpretation.intent == ConversationIntent.UNKNOWN
            and self.interpreter._is_contextual_revision(normalized)
            and self._has_preferences(preferences)
        ):
            interpretation.contextual_revision = True

        self._response_intent = interpretation.intent
        decision = DecisionRouter.decide(
            normalized,
            interpretation,
            entity=entity,
            budget=budget_request,
            has_reference=bool(
                self._session_state.get_last_recommendation_ids()
                or (
                    interpretation.contextual_revision
                    and (pending_question or old_follow_up or preferences.tags)
                )
            ),
        )

        if open_followup_answer:
            decision = RoutingDecision(RoutingDecision.LOCAL, 'resolved_followup')

        if decision.route == RoutingDecision.CLARIFY:
            if decision.reason == 'budget_conflict':
                return self._budget_clarification(preferences, budget_request.clarification)

            return self._routing_clarification(preferences, decision.reason, entity)

        if decision.route == RoutingDecision.AI_ASSISTED:
            if decision.task == 'rerank':
                return self._subjective_response(normalized, preferences, budget_request)

            if self._current_context is not None or not self._consume_gemini_call():
                fallback_event('interpretation')

                return self._routing_clarification(preferences, 'proposal_unavailable', entity)

            if decision.task == 'classify_entity' and entity is not None:
                classified = self.gemini_interpreter.classify_entity(
                    entity.requested_entity, normalized
                )

                if classified is None or classified.domain_status == 'AMBIGUOUS_REQUEST':
                    fallback_event('interpretation')

                    return self._routing_clarification(preferences, 'proposal_unavailable', entity)

                return self._entity_response(
                    classified, preferences, interpretation, budget=budget_request.constraint
                )

            proposal = self._interpret_semantic(normalized, interpretation, preferences)
            previous = self._search_constraints()

            if proposal is None or not DecisionRouter.accepts_proposal(
                proposal,
                allowed_tags=self.tag_extractor.get_allowed_tags(),
                local=interpretation,
                hard_exclusions=preferences.excluded_tags | set(previous.excluded_tags),
            ):
                fallback_event('interpretation')

                return self._routing_clarification(preferences, 'proposal_unavailable')

            if previous.budget is not None or previous.max_price is not None:
                proposal.contextual_revision = True

            interpretation = proposal
            self._response_intent = proposal.intent
            # The optional entity classifier and preference interpreter share one
            # routing decision, never two speculative provider calls in one turn.
            entity = None

        if named_reference or (
            interpretation.intent
            in {
                ConversationIntent.UNKNOWN,
                ConversationIntent.RECOMMEND,
                ConversationIntent.CATALOG_QUESTION,
                ConversationIntent.UPDATE_PREFERENCES,
                ConversationIntent.OUT_OF_SCOPE,
                ConversationIntent.GREETING,
            }
            and not interpretation.contextual_revision
        ):
            if entity is not None:
                if entity.domain_status == "IN_CATALOG" and budget_request.clarification:
                    return self._budget_clarification(preferences, budget_request.clarification)

                if entity.domain_status == "IN_CATALOG" and budget_request.kind != "none":
                    return self._budget_response(
                        budget_request, normalized, preferences, interpretation, entity=entity
                    )

                return self._entity_response(
                    entity, preferences, interpretation, budget=budget_request.constraint
                )

        item_restriction = bool(
            interpretation.excluded_tags
        ) and interpretation.excluded_tags <= set(
            self._session_state.contexts()['active']['item_excluded_tags']
        )

        if (
            (interpretation.tags or interpretation.category)
            and not item_restriction
            and interpretation.intent
            not in {
                ConversationIntent.REJECT_RECOMMENDATION,
                ConversationIntent.REQUEST_ALTERNATIVES,
            }
        ):
            self._session_state.set_entity_ids([])

        if budget_request.kind != "none" and interpretation.intent not in {
            ConversationIntent.RESET,
            ConversationIntent.OUT_OF_SCOPE,
            ConversationIntent.HELP,
        }:
            return self._budget_response(budget_request, normalized, preferences, interpretation)

        if interpretation.intent == ConversationIntent.RETRY_SEARCH:
            updated = self._apply_interpretation(preferences, interpretation)
            constraints = self._constraints_for_interpretation(interpretation)
            self._session_state.set_last_question(None)

            return self._recommend(
                updated,
                normalized,
                response_kind="retry",
                constraints=constraints,
            )

        if interpretation.intent == ConversationIntent.CATALOG_QUESTION:
            return self._answer_catalog_question(
                preferences,
                interpretation,
                normalized,
            )

        if open_followup_answer:
            self._session_state.set_last_question(None)

            return self._recommend(preferences, normalized)

        if interpretation.intent == ConversationIntent.RESET:
            self.reset()

            return self._question()

        if interpretation.intent == ConversationIntent.GREETING:
            return self._greeting_response(preferences)

        if interpretation.intent == ConversationIntent.HELP:
            self._response_purpose = 'help'

            return {
                "message": self._responses.choose(
                    'help',
                    (
                        "Aku bisa bantu cari menu yang cocok. Coba bilang misalnya 'pedas', 'ayam', 'nasi', atau 'yang murah'.",
                        "Sebutkan makanan, rasa, atau batas harga yang kamu inginkan. Aku akan mencari pilihan dari menu kami.",
                        "Kamu bisa meminta jenis makanan, memberi batas budget, atau mengubah pilihan sebelumnya.",
                    ),
                ),
                "state": session_state.get("state", "COLLECTING_PREFERENCES"),
                "preferences": preferences.to_dict(
                    state=session_state.get("state", "COLLECTING_PREFERENCES")
                ),
                "recommendations": [],
                "quick_replies": [
                    self._quick_reply("🌶️ Pedas", "Pengen yang pedas"),
                    self._quick_reply("🍗 Ayam", "Aku mau ayam"),
                    self._quick_reply("💸 Murah", "Yang murah saja"),
                ],
            }

        if interpretation.intent == ConversationIntent.OUT_OF_SCOPE:
            self._response_purpose = 'nonfood'

            return {
                "message": self._responses.choose(
                    'out_of_scope',
                    (
                        "Aku fokus bantu kamu pilih menu di sini. Coba kasih tahu kamu lagi ingin makan atau minum apa.",
                        "Topik itu di luar informasi menu yang bisa kubantu. Kalau ingin makanan atau minuman, sebutkan seleramu, ya.",
                        "Untuk saat ini aku bisa membantu pilihan menu restoran. Mau mencari makanan atau minuman?",
                    ),
                ),
                "state": "COLLECTING_PREFERENCES",
                "preferences": preferences.to_dict(state="COLLECTING_PREFERENCES"),
                "recommendations": [],
                "quick_replies": [
                    self._quick_reply("🍚 Makanan berat", "Makanan berat"),
                    self._quick_reply("🍟 Camilan", "Camilan"),
                    self._quick_reply("🥤 Minuman", "Minuman"),
                ],
            }

        missing_reference = (
            interpretation.intent == ConversationIntent.UNKNOWN
            and interpretation.contextual_reference is not None
            and not interpretation.contextual_revision
        )

        if interpretation.intent == ConversationIntent.UNKNOWN and not missing_reference:
            state = session_state.get("state", "COLLECTING_PREFERENCES")

            if not self._has_preferences(preferences):
                state = "COLLECTING_PREFERENCES"

            return {
                "message": self._unknown_response(normalized),
                "state": state,
                "preferences": preferences.to_dict(state=state),
                "recommendations": [],
                "quick_replies": [
                    self._quick_reply("🌶️ Pedas", "Pengen yang pedas"),
                    self._quick_reply("🍗 Ayam", "Aku mau ayam"),
                    self._quick_reply("💸 Murah", "yang murah"),
                ],
            }

        if interpretation.intent == ConversationIntent.SELECT_RECOMMENDATION or missing_reference:
            match = self._select_previous_recommendation(interpretation, session_state)

            if match is None:
                return {
                    "message": "Aku belum menemukan menu yang kamu maksud di pilihan sebelumnya. Mau aku carikan rekomendasi lagi?",
                    "state": session_state.get("state", "COLLECTING_PREFERENCES"),
                    "preferences": preferences.to_dict(
                        state=session_state.get("state", "COLLECTING_PREFERENCES")
                    ),
                    "recommendations": [],
                    "quick_replies": [
                        self._quick_reply("🔄 Cari menu lagi", "Cari menu lain", action="more"),
                        self._quick_reply("🍗 Ayam", "Aku mau ayam"),
                    ],
                }

            self._response_purpose = 'selection'
            self._session_state.set_focus(match.item.pk)
            self._session_state.record_recommendations(
                [match.item.pk], shown_ids=self._session_state.get_shown_ids() + [match.item.pk]
            )

            return {
                "message": "Ini menu yang kamu maksud dari rekomendasi sebelumnya 😊",
                "state": session_state.get("state", "RECOMMENDING"),
                "preferences": preferences.to_dict(
                    state=session_state.get("state", "RECOMMENDING")
                ),
                "recommendations": [match],
                "quick_replies": [],
            }

        if interpretation.intent == ConversationIntent.REQUEST_ALTERNATIVES:
            if not self._has_preferences(preferences) and not self._has_active_search():
                return self._question(confused=True)

            return self._recommend(preferences, normalized, more=True)

        if interpretation.intent == ConversationIntent.REJECT_RECOMMENDATION:
            rejected_ids = (
                list(interpretation.rejected_menu_ids) or self._session_state.get_rejected_ids()
            )

            if not rejected_ids:
                return {
                    "message": "Boleh kasih tahu preferensimu yang baru, atau aku bisa bantu cari yang lain.",
                    "state": session_state.get("state", "COLLECTING_PREFERENCES"),
                    "preferences": preferences.to_dict(
                        state=session_state.get("state", "COLLECTING_PREFERENCES")
                    ),
                    "recommendations": [],
                    "quick_replies": [
                        self._quick_reply("🌶️ Pedas", "Pengen yang pedas"),
                        self._quick_reply("🍗 Ayam", "Aku mau ayam"),
                    ],
                }

            self._session_state.remember_rejected(rejected_ids)
            result = self._recommend(preferences, normalized, more=True, exclude_ids=rejected_ids)
            result["message"] = (
                self._deterministic_variant(
                    normalized,
                    (
                        "Oke, kita cari yang lain 😄",
                        "Siap, yang tadi kita lewati dulu.",
                        "Belum cocok? Kita coba pilihan lain.",
                    ),
                )
                + "\n"
                + result["message"]
            )

            return result

        if interpretation.intent == ConversationIntent.CONFIRM:
            if session_state.get("last_question") == "meal_type":
                if "heavy_meal" in preferences.tags:
                    return self._ask_base(preferences)

                return self._recommend(preferences, normalized)

            if session_state.get("last_question") == "base":
                return self._recommend(preferences, normalized)

            return self._recommend(preferences, normalized)

        if interpretation.intent in {
            ConversationIntent.RECOMMEND,
            ConversationIntent.UPDATE_PREFERENCES,
            ConversationIntent.REMOVE_PREFERENCES,
            ConversationIntent.REPLACE_PREFERENCES,
        }:
            updated = self._apply_interpretation(preferences, interpretation)
            constraints = self._constraints_for_interpretation(
                interpretation,
                old_follow_up=old_follow_up,
            )

            if (
                interpretation.intent == ConversationIntent.UPDATE_PREFERENCES
                and not self._has_preferences(updated)
            ):
                if interpretation.clear_moods:
                    response = self._question()
                    self._save(updated, "COLLECTING_PREFERENCES")

                    return response

                return self._question(confused=True)

            self._session_state.set_last_question(None)
            self._session_state.save_search(constraints)
            updated.mood_tags = self.mood_resolver.resolve(
                updated.moods, explicit_tags=updated.tags
            )

            if (
                old_follow_up == "meal_type"
                and "heavy_meal" in updated.tags
                and not updated.tags.intersection({"rice", "noodle", "snack"})
            ):
                return self._ask_base(updated)

            only_spicy = (
                updated.tags.intersection({"spicy"}) == {"spicy"}
                and len(updated.tags) == 1
                and not updated.moods
                and updated.max_price is None
                and not updated.prefer_affordable
                and not updated.excluded_tags
                and not updated.soft_excluded_tags
                and not updated.category
            )

            if only_spicy and old_follow_up is None:
                return self._ask_meal_type(updated)

            if (
                not self._has_preferences(updated)
                and constraints.budget is None
                and constraints.max_price is None
            ):
                self._save(updated, "COLLECTING_PREFERENCES")

                if interpretation.clear_moods:
                    response = self._question()
                    self._save(updated, "COLLECTING_PREFERENCES")

                    return response

                return self._question()

            self._save(updated, "RECOMMENDING")
            result = self._recommend(
                updated,
                normalized,
                response_kind=(
                    "correction"
                    if interpretation.intent == ConversationIntent.REPLACE_PREFERENCES
                    else (
                        "removal"
                        if interpretation.intent == ConversationIntent.REMOVE_PREFERENCES
                        else "recommendation"
                    )
                ),
                constraints=constraints,
            )

            return result

        if more:
            if not self._has_preferences(preferences) and not self._has_active_search():
                return self._question(confused=True)

            return self._recommend(preferences, normalized, more=True)

        if not self._has_preferences(preferences):
            return self._question()

        return self._recommend(preferences, normalized)
