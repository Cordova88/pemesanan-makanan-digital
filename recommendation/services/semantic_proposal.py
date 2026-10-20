"""H2 ephemeral proposal boundary. No provider calls, ORM access or state writes."""
from collections.abc import Collection, Iterable, Mapping
from copy import deepcopy
from decimal import Decimal
import json
import re
from typing import ClassVar

from .budget import BudgetRequest
from .conversation_interpreter import ConversationInterpretation, PreferenceOperation
from .entity_resolver import EntityResolution
from .language import IndonesianPriceParser
from .plan_interpreter import PlanDelta, PlanInterpreter


class SemanticEvidence:
    """Trusted local snapshot. Ref names are request-local, never session IDs."""

    def __init__(
        self, message: str, local: ConversationInterpretation, *,
        allowed_tags: Collection[str], hard_exclusions: Collection[str],
        category_names: Iterable[str], context_action: str, constraint_scope: str,
        revision: int = 0, context_ref: str = 'active',
        entity: EntityResolution | None = None, entity_category: str | None = None,
    ) -> None:
        if (type(message) is not str or not message.strip() or len(message) > 500
                or type(revision) is not int or not 0 <= revision <= 2**53-1
                or type(context_ref) is not str or not re.fullmatch(r'active|previous[1-4]', context_ref)
                or (context_action == 'REFER_TO_PREVIOUS') != context_ref.startswith('previous')):
            raise ValueError('Invalid local evidence boundary')
        try:
            message.encode('utf-8')
        except UnicodeError as exc:
            raise ValueError('Invalid message encoding') from exc
        if not isinstance(local, ConversationInterpretation):
            raise ValueError('Expected local interpretation')
        # Reuse existing metadata validation rather than a second enum vocabulary.
        ConversationInterpretation('UNKNOWN', context_action=context_action, constraint_scope=constraint_scope)
        if type(context_action) is not str or type(constraint_scope) is not str:
            raise ValueError('Unresolved local scope')
        if isinstance(category_names, str):
            raise ValueError('Expected category inventory')
        names = set(category_names)
        if len(names) > 32 or any(type(n) is not str or not 1 <= len(n) <= 100 for n in names):
            raise ValueError('Invalid category inventory')
        if isinstance(allowed_tags, str) or isinstance(hard_exclusions, str):
            raise ValueError('Expected tag inventories')
        tags, hard = frozenset(allowed_tags), frozenset(hard_exclusions)
        if any(len(values) > 256 or any(type(t) is not str or not re.fullmatch(r'[a-zA-Z0-9_-]{1,50}', t)
                                       for t in values) for values in (tags, hard)):
            raise ValueError('Invalid tag inventory')
        parser = IndonesianPriceParser()
        planner = PlanInterpreter(parser, names)
        budget, plan = parser.parse(message), planner.interpret(message)
        normalized = parser.normalize_money_input(message)
        mentions = parser.numeric_roles(message)
        if len(mentions) > 16:
            raise ValueError('Too many numeric mentions')
        roles = {f'r{i}': name for i, name in enumerate(sorted(names), 1)}
        role_refs = {name: ref for ref, name in roles.items()}
        entities: dict[str, tuple[int, str]] = {}
        if entity is not None and entity.domain_status == 'IN_CATALOG' and len(entity.menu_ids) == 1:
            identifier = entity.menu_ids[0]
            if type(identifier) is not int or identifier <= 0 or entity_category not in names:
                raise ValueError('Unproven local catalog role')
            if local.target_menu_id is not None and local.target_menu_id != identifier:
                raise ValueError('Contradictory local catalog target')
            entities['e1'] = (identifier, entity_category)
        bindings: set[tuple[str, str, str]] = set()
        for i, mention in enumerate(mentions, 1):
            ref, value = f'n{i}', mention.value
            if mention.role == 'MONEY':
                # Equal literals with distinct purposes require positional proof
                # that the old parser does not expose. Never guess by value alone.
                if sum(m.role == 'MONEY' and m.value == value for m in mentions) > 1:
                    continue
                if plan.implicit_total == value or plan.total_budget == value:
                    if constraint_scope == 'PLAN_TOTAL':bindings.add((ref, 'TOTAL', 'plan'))
                elif plan.per_person_budget == value or budget.scope == 'PER_PERSON' and budget.amount == value:
                    if constraint_scope == 'PLAN_TOTAL':bindings.add((ref, 'PER_PERSON', 'plan'))
                elif budget.scope in {'PLAN_TOTAL', 'GROUP_TOTAL'} and budget.amount == value:
                    if constraint_scope == 'PLAN_TOTAL':bindings.add((ref, 'TOTAL', 'plan'))
                elif budget.soft_target == value:
                    if constraint_scope in {'CURRENT_SEARCH', 'SPECIFIC_ITEM'}:bindings.add((ref, 'SOFT_TARGET', context_ref))
                elif budget.scope == 'CURRENT_SEARCH' and budget.constraint is not None:
                    if constraint_scope in {'CURRENT_SEARCH', 'SPECIFIC_ITEM'}:
                        if budget.constraint.maximum == value:bindings.add((ref, 'UNIT_MAX', context_ref))
                        if budget.constraint.minimum == value:bindings.add((ref, 'UNIT_MIN', context_ref))
                if constraint_scope == 'PLAN_TOTAL':
                    for name, amount in plan.category_budgets.items():
                        if Decimal(amount) == value:bindings.add((ref, 'TOTAL', role_refs[name]))
            elif value == value.to_integral_value() and 1 <= value <= 99:
                if (mention.role == 'PERSON_COUNT' and constraint_scope == 'PLAN_TOTAL'
                        and value in {plan.person_count, budget.person_count}):
                    bindings.add((ref, 'PERSON_COUNT', 'plan'))
                if mention.role == 'QUANTITY':
                    if (entities and plan.quantity == value
                            and constraint_scope in {'SPECIFIC_ITEM', 'PLAN_TOTAL'}):
                        bindings.add((ref, 'QUANTITY', 'e1'))
                    suffix = re.sub(r'^\s*(?:porsi|gelas|buah|item|menu)\s+', '', normalized[mention.end:])
                    for term, name in planner.roles.items():
                        if (constraint_scope == 'PLAN_TOTAL' and plan.role_quantities.get(name) == value
                                and re.match(r'^\s*' + re.escape(term) + r'\b', suffix)):
                            bindings.add((ref, 'QUANTITY', role_refs[name]))
        self.__snapshot = deepcopy(dict(
            revision=revision, context_action=context_action, constraint_scope=constraint_scope,
            context_ref=context_ref, local=local, plan=plan, budget=budget,
            tags=tags, hard=hard | frozenset(local.excluded_tags), roles=roles, entities=entities,
            bindings=bindings, blocked=bool(plan.clarification or budget.scope_ambiguous
                                          or budget.kind in {'invalid', 'ambiguous'}),
        ))

    @property
    def local_interpretation(self) -> ConversationInterpretation:
        return deepcopy(self.__snapshot['local'])

    def _snapshot(self) -> dict:
        return deepcopy(self.__snapshot)

    def provider_packet(self, request: str) -> dict:
        """Explicit allowlist; never serialize the local DTOs or session graph."""
        e = self.__snapshot
        return dict(proposal_version=3, request=request[:500],
            context_action=e['context_action'], constraint_scope=e['constraint_scope'],
            context_ref=e['context_ref'], allowed_tags=sorted(e['tags']),
            hard_excluded_tags=sorted(e['hard']),
            local_tags=sorted(e['local'].tags),
            role_refs=dict(e['roles']), entity_refs={ref: {'role_ref': next(
                role for role, name in e['roles'].items() if name == category)}
                for ref, (_, category) in e['entities'].items()},
            allowed_numeric_bindings=[dict(mention_ref=ref, purpose=purpose, owner_ref=owner)
                for ref, purpose, owner in sorted(e['bindings'])])


class SemanticProposal:
    """Validated snapshot proposal, not permission to commit or transact."""
    MAX_BYTES: ClassVar[int] = 12000
    MAX_DEPTH: ClassVar[int] = 8
    FIELDS: ClassVar[frozenset[str]] = frozenset({
        'proposal_version', 'intent', 'context_action', 'constraint_scope', 'context_ref',
        'preference_operations', 'entity_roles', 'numeric_bindings', 'clarification_key',
    })
    CLARIFICATIONS: ClassVar[frozenset[str]] = frozenset({'request', 'budget_scope', 'menu_reference', 'serving_mode', 'category'})

    def __init__(self, interpretation: ConversationInterpretation, plan_delta: PlanDelta,
                 budget: BudgetRequest, clarification_key: str | None, numeric_bindings: list[dict]) -> None:
        self.__interpretation = deepcopy(interpretation)
        self.__plan_delta = deepcopy(plan_delta)
        self.__budget = deepcopy(budget)
        self.__clarification_key = clarification_key
        self.__numeric_bindings = deepcopy(numeric_bindings)

    @property
    def interpretation(self) -> ConversationInterpretation:
        return deepcopy(self.__interpretation)

    @property
    def plan_delta(self) -> PlanDelta:
        return deepcopy(self.__plan_delta)

    @property
    def budget(self) -> BudgetRequest:
        return deepcopy(self.__budget)

    @property
    def clarification_key(self) -> str | None:
        return self.__clarification_key

    @property
    def numeric_bindings(self) -> list[dict]:
        return deepcopy(self.__numeric_bindings)

    @staticmethod
    def _unique_object(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:raise ValueError('Duplicate key')
            result[key] = value
        return result

    @staticmethod
    def _constant(value: str) -> None:
        raise ValueError('Non-finite number')

    @classmethod
    def _decode(cls, raw: object) -> dict:
        if type(raw) is not str or len(raw.encode('utf-8')) > cls.MAX_BYTES:
            raise ValueError('Invalid response boundary')
        depth, quoted, escaped = 0, False, False
        for char in raw:
            if quoted:
                if escaped:escaped = False
                elif char == '\\':escaped = True
                elif char == '"':quoted = False
            elif char == '"':quoted = True
            elif char in '[{':
                depth += 1
                if depth > cls.MAX_DEPTH:raise ValueError('Excessive nesting')
            elif char in ']}':depth -= 1
        data = json.loads(raw, object_pairs_hook=cls._unique_object, parse_constant=cls._constant)
        if type(data) is not dict or set(data) != cls.FIELDS:
            raise ValueError('Invalid fields')
        return data

    @staticmethod
    def _rows(value: object) -> list:
        if type(value) is not list or len(value) > 8:raise ValueError('Invalid row count')
        return value

    @staticmethod
    def _tags(value: object, allowed: frozenset[str]) -> set[str]:
        if type(value) is not list or len(value) > 8 or any(type(t) is not str or t not in allowed for t in value):
            raise ValueError('Invalid tags')
        if len(value) != len(set(value)):raise ValueError('Duplicate tags')
        return set(value)

    @classmethod
    def parse_and_validate(cls, raw: object, evidence: SemanticEvidence, *, current_revision: int,
                           available_menu_ids: Collection[int] = (), active_categories: Collection[str] = (),
                           catalog_roles: Mapping[int, str] | None = None) -> 'SemanticProposal | None':
        try:
            if not isinstance(evidence, SemanticEvidence):return None
            e, data = evidence._snapshot(), cls._decode(raw)
            if (type(current_revision) is not int or current_revision != e['revision']
                    or type(data['proposal_version']) is not int or data['proposal_version'] != 3
                    or any(type(data[k]) is not str or data[k] != e[k] for k in ('context_action', 'constraint_scope', 'context_ref'))):
                return None
            if isinstance(active_categories, str) or any(type(i) is not int or i <= 0 for i in available_menu_ids) or any(type(c) is not str for c in active_categories):return None
            if catalog_roles is not None and (not isinstance(catalog_roles, Mapping)
                    or any(type(i) is not int or i <= 0 or type(c) is not str for i,c in catalog_roles.items())):return None
            intent = data['intent']
            if type(intent) is not str or intent not in {'RECOMMEND', 'UPDATE_PREFERENCES', 'REMOVE_PREFERENCES', 'REPLACE_PREFERENCES', 'SELECT_RECOMMENDATION', 'UNKNOWN'}:
                return None
            if e['local'].intent in {'RESET', 'GREETING', 'HELP', 'OUT_OF_SCOPE', 'REJECT_RECOMMENDATION',
                                     'REQUEST_ALTERNATIVES', 'CONFIRM', 'CATALOG_QUESTION', 'RETRY_SEARCH'}:
                return None
            ops = cls._rows(data['preference_operations'])
            entities, numbers = cls._rows(data['entity_roles']), cls._rows(data['numeric_bindings'])
            key = data['clarification_key']
            if key is not None:
                if type(key) is not str or key not in cls.CLARIFICATIONS:return None
                if intent != 'UNKNOWN' or data['context_action'] != 'CLARIFY' or ops or entities or numbers:return None
                result = ConversationInterpretation('UNKNOWN', source='gemini',
                    context_action=e['context_action'], constraint_scope=e['constraint_scope'])
                return cls(result, PlanDelta(), BudgetRequest(), key, [])
            if (e['blocked'] or intent == 'UNKNOWN' or data['context_action'] == 'CLARIFY'
                    or e['constraint_scope'] == 'SAFETY_RESTRICTION'):return None
            def fresh(owner: str) -> bool:
                if owner in e['entities']:
                    identifier, category = e['entities'][owner]
                    return (identifier in available_menu_ids and category in active_categories
                            and catalog_roles is not None and catalog_roles.get(identifier) == category)
                if owner in e['roles']:return e['roles'][owner] in active_categories
                return owner in {'plan', e['context_ref']}
            seen = set()
            for row in numbers:
                if type(row) is not dict or set(row) != {'mention_ref', 'purpose', 'owner_ref'}:return None
                if any(type(v) is not str for v in row.values()):return None
                binding = (row['mention_ref'], row['purpose'], row['owner_ref'])
                if row['mention_ref'] in seen or binding not in e['bindings'] or not fresh(row['owner_ref']):return None
                seen.add(row['mention_ref'])
            selected = set()
            for row in entities:
                if type(row) is not dict or set(row) != {'entity_ref', 'role_ref', 'operation'}:return None
                if any(type(v) is not str for v in row.values()):return None
                er, rr = row['entity_ref'], row['role_ref']
                expected = {'ADD_TO_CONTEXT':'ADD', 'CORRECT_PREVIOUS':'REPLACE'}.get(e['context_action'], 'SELECT')
                if (er in selected or er not in e['entities'] or rr not in e['roles'] or not fresh(er)
                        or e['entities'][er][1] != e['roles'][rr] or row['operation'] != expected):return None
                selected.add(er)
            local = e['local']
            if local.intent == 'SELECT_RECOMMENDATION' and intent != local.intent:return None
            if selected and (intent != 'SELECT_RECOMMENDATION' or local.intent != intent):return None
            added, hard, soft = set(local.tags), set(local.excluded_tags), set(local.soft_excluded_tags)
            proven_remove = set(t for op in local.operations if op.action == 'REPLACE' for t in op.remove_tags)
            used_tags: set[str] = set()
            for row in ops:
                if type(row) is not dict or set(row) != {'action', 'tag_ids', 'remove_tag_ids'}:return None
                action = row['action']
                tags, removed = cls._tags(row['tag_ids'], e['tags']), cls._tags(row['remove_tag_ids'], e['tags'])
                if action not in {'ADD', 'REMOVE', 'SOFT_REMOVE', 'REPLACE', 'KEEP'} or used_tags & tags:return None
                if action == 'KEEP' and (tags or removed) or action != 'REPLACE' and removed:return None
                if action == 'REPLACE' and (intent != 'REPLACE_PREFERENCES' or not removed or not removed <= proven_remove):return None
                if removed & e['hard']:return None
                if action in {'REMOVE', 'SOFT_REMOVE'} and intent != 'REMOVE_PREFERENCES':return None
                if action == 'REMOVE' and not tags <= local.excluded_tags:return None
                used_tags |= tags
                if action in {'ADD','REPLACE'}:added |= tags
                elif action == 'REMOVE':hard |= tags
                elif action == 'SOFT_REMOVE':soft |= tags
            if added & (hard | soft) or (added | soft) & e['hard']:return None
            if intent == 'REPLACE_PREFERENCES' and not proven_remove:return None
            if intent == 'REMOVE_PREFERENCES' and not (hard or soft):return None
            result = deepcopy(local)
            if intent == 'SELECT_RECOMMENDATION':
                if local.intent != intent or not selected or ops:return None
            else:
                normalized_ops = [PreferenceOperation('REPLACE' if proven_remove else 'ADD',tuple(sorted(added)),tuple(sorted(proven_remove)))] if added or proven_remove else []
                if hard:normalized_ops.append(PreferenceOperation('REMOVE',tuple(sorted(hard))))
                if soft:normalized_ops.append(PreferenceOperation('SOFT_REMOVE',tuple(sorted(soft))))
                if not normalized_ops:normalized_ops = [PreferenceOperation('KEEP')]
                candidate = ConversationInterpretation(intent,operations=normalized_ops,tags=added,excluded_tags=hard,
                    soft_excluded_tags=soft,source='gemini',context_action=e['context_action'],constraint_scope=e['constraint_scope'])
                local.context_action, local.constraint_scope = e['context_action'], e['constraint_scope']
                from .decision_router import DecisionRouter
                if not DecisionRouter.accepts_proposal(candidate,allowed_tags=set(e['tags']),local=local,hard_exclusions=set(e['hard'])):return None
                if not (added or hard or soft or numbers or entities):return None
                result.tags, result.excluded_tags, result.soft_excluded_tags = added, hard, soft
                result.operations = normalized_ops
                result.intent = local.intent if local.intent in {'UPDATE_PLAN','UPDATE_BUDGET'} else intent
            result.source = 'gemini'
            result.message_is_meaningful = True
            result.context_action, result.constraint_scope = e['context_action'], e['constraint_scope']
            if selected:result.target_menu_id = e['entities'][next(iter(selected))][0]
            return cls(result, e['plan'], e['budget'], None, numbers)
        except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
            # Reject atomically; no raw prompt/output/error logging or state writes.
            return None
