"""Pure routing policy; never calls a provider, queries the DB, or writes state."""
import re
from collections.abc import Collection, Mapping
from typing import ClassVar

from .semantic_proposal import SemanticEvidence, SemanticProposal

from .budget import BudgetRequest
from .conversation_interpreter import ConversationIntent, ConversationInterpretation, PreferenceOperation
from .entity_resolver import EntityResolution
from .language import normalize_text


class RoutingDecision:
    LOCAL: ClassVar[str] = 'LOCAL'
    AI_ASSISTED: ClassVar[str] = 'AI_ASSISTED'
    CLARIFY: ClassVar[str] = 'CLARIFY'

    def __init__(self, route: str, reason: str, *, task: str = 'interpret') -> None:
        if route not in {self.LOCAL, self.AI_ASSISTED, self.CLARIFY}:
            raise ValueError('Invalid route')
        self.route: str = route
        self.reason: str = reason
        self.task: str = task


class DecisionRouter:
    @staticmethod
    def validate_proposal_v3(raw: object, evidence: SemanticEvidence, *, current_revision: int,
                             available_menu_ids: Collection[int] = (), active_categories: Collection[str] = (),
                             catalog_roles: Mapping[int, str] | None = None) -> SemanticProposal | None:
        """Explicit offline v3 boundary; the active v1/v2 route is unchanged."""
        return SemanticProposal.parse_and_validate(raw, evidence, current_revision=current_revision,
            available_menu_ids=available_menu_ids, active_categories=active_categories, catalog_roles=catalog_roles)

    # These identify unresolved meaning, not authority to modify preferences.
    SUBJECTIVE: ClassVar[re.Pattern[str]] = re.compile(
        r'\b(?:eneg|berminya\w*|bikin nagih|nemenin|menemani|nugas|cepat lapar|'
        r'tetap mengenyangkan|cukup mengenyangkan)\b'
    )
    FOOD_REQUEST: ClassVar[re.Pattern[str]] = re.compile(
        r'\b(?:makan\w*|minum\w*|menu|masakan|ayam|nasi|mie|pedas|manis|gurih|'
        r'ringan|kenyang|pengen|mau|cari|mirip)\b'
    )

    @classmethod
    def decide(
        cls, message: str, interpretation: ConversationInterpretation, *,
        entity: EntityResolution | None = None, budget: BudgetRequest | None = None,
        has_reference: bool = False,
    ) -> RoutingDecision:
        text = normalize_text(message)
        if len(text) > 500:
            return RoutingDecision(RoutingDecision.CLARIFY, 'message_too_long')
        if budget is not None and budget.clarification:
            return RoutingDecision(RoutingDecision.CLARIFY, 'budget_conflict')
        if entity is not None and entity.domain_status == 'AMBIGUOUS_CATALOG':
            return RoutingDecision(RoutingDecision.CLARIFY, 'ambiguous_catalog')
        if interpretation.contextual_reference and not has_reference:
            return RoutingDecision(RoutingDecision.CLARIFY, 'missing_reference')
        if entity is not None and entity.domain_status not in {'AMBIGUOUS_REQUEST'}:
            return RoutingDecision(RoutingDecision.LOCAL, 'resolved_entity')
        if interpretation.intent in {
            ConversationIntent.RESET, ConversationIntent.GREETING, ConversationIntent.HELP,
            ConversationIntent.OUT_OF_SCOPE, ConversationIntent.SELECT_RECOMMENDATION,
            ConversationIntent.REJECT_RECOMMENDATION, ConversationIntent.REQUEST_ALTERNATIVES,
            ConversationIntent.CONFIRM,
        }:
            return RoutingDecision(RoutingDecision.LOCAL, 'resolved_dialog_action')
        unresolved_subjective = cls.SUBJECTIVE.search(text)
        if unresolved_subjective and not unresolved_subjective.group().startswith('berminya'):
            return RoutingDecision(RoutingDecision.AI_ASSISTED, 'subjective_request', task='rerank')
        if (interpretation.contextual_revision and interpretation.intent != ConversationIntent.UNKNOWN
                and interpretation.operations):
            return RoutingDecision(RoutingDecision.LOCAL, 'resolved_revision')
        if unresolved_subjective:
            return RoutingDecision(RoutingDecision.AI_ASSISTED, 'subjective_request', task='rerank')
        if entity is not None and entity.domain_status == 'AMBIGUOUS_REQUEST':
            return RoutingDecision(RoutingDecision.AI_ASSISTED, 'unresolved_entity', task='classify_entity')
        if budget is not None and budget.kind != 'none':
            return RoutingDecision(RoutingDecision.LOCAL, 'resolved_budget')
        if interpretation.contextual_revision:
            if interpretation.intent != ConversationIntent.UNKNOWN and interpretation.operations:
                return RoutingDecision(RoutingDecision.LOCAL, 'resolved_revision')
            return RoutingDecision(RoutingDecision.AI_ASSISTED, 'unresolved_revision')
        if interpretation.intent != ConversationIntent.UNKNOWN:
            return RoutingDecision(RoutingDecision.LOCAL, 'resolved_preferences')
        if cls.FOOD_REQUEST.search(text):
            return RoutingDecision(RoutingDecision.AI_ASSISTED, 'unresolved_food_request')
        return RoutingDecision(RoutingDecision.CLARIFY, 'unknown_request')

    @staticmethod
    def accepts_proposal(
        proposal: ConversationInterpretation, *, allowed_tags: set[str],
        local: ConversationInterpretation, hard_exclusions: set[str],
    ) -> bool:
        """Validate the shared action contract after the strict wire-schema check.

        AI may propose preferences, never catalog identity, reference or money.
        Those fields remain owned by the local resolver and budget parser.
        """
        if proposal.source != 'gemini' or proposal.intent not in {
            ConversationIntent.RECOMMEND, ConversationIntent.UPDATE_PREFERENCES,
            ConversationIntent.REMOVE_PREFERENCES, ConversationIntent.REPLACE_PREFERENCES,
        }:
            return False
        if (proposal.context_action is not None and proposal.context_action != local.context_action
                or proposal.constraint_scope is not None and proposal.constraint_scope != local.constraint_scope):
            return False
        if (proposal.target_menu_id is not None or proposal.rejected_menu_ids
                or proposal.contextual_reference is not None or proposal.category is not None
                or proposal.max_price is not None or proposal.clear_max_price):
            return False
        collections = (proposal.tags, proposal.excluded_tags, proposal.soft_excluded_tags)
        if any(type(values) is not set or not values <= allowed_tags for values in collections):
            return False
        if proposal.tags & (proposal.excluded_tags | proposal.soft_excluded_tags):
            return False
        if (proposal.tags | proposal.soft_excluded_tags) & (hard_exclusions - local.tags):
            return False
        if not local.excluded_tags <= proposal.excluded_tags:
            return False
        if not local.tags <= proposal.tags:
            return False
        operations = {'ADD', 'REMOVE', 'SOFT_REMOVE', 'REPLACE', 'KEEP'}
        if not proposal.operations or any(
            not isinstance(op, PreferenceOperation) or op.action not in operations
            or type(op.tags) is not tuple or type(op.remove_tags) is not tuple
            for op in proposal.operations
        ):
            return False
        added, removed, soft = set(), set(), set()
        for op in proposal.operations:
            if not set(op.tags + op.remove_tags) <= allowed_tags:
                return False
            if op.action in {'ADD', 'REPLACE'}:
                added.update(op.tags)
            elif op.action == 'REMOVE':
                removed.update(op.tags)
            elif op.action == 'SOFT_REMOVE':
                soft.update(op.tags)
            elif op.tags or op.remove_tags:
                return False
            if op.remove_tags and op.action != 'REPLACE':
                return False
        return (added, removed, soft) == (proposal.tags, proposal.excluded_tags, proposal.soft_excluded_tags)
