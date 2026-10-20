"""Persistence of chatbot state in an externally owned Django session."""
from typing import ClassVar, cast
from time import time
from copy import deepcopy

from django.contrib.sessions.backends.base import SessionBase
from django.conf import settings

from .recommendation import SearchConstraints
from .tag_extractor import Preferences, PreferencesPayload
from .mood_extractor import UserContext
from .budget import BudgetConstraint
from decimal import Decimal


class ConversationStatePayload(PreferencesPayload, total=False):
    last_question: str | None
    last_recommendations: list[int]
    shown_recommendation_ids: list[int]


class ConversationSession:
    STATE_KEY: ClassVar[str] = "recommendation_state"
    SHOWN_KEY: ClassVar[str] = "recommendation_shown"
    SEARCH_KEY: ClassVar[str] = "recommendation_search"
    LAST_RESULT_EMPTY_KEY: ClassVar[str] = "recommendation_last_result_empty"
    GEMINI_CALLS_KEY: ClassVar[str] = "gemini_calls"
    TEMP_CONTEXT_KEY: ClassVar[str] = "recommendation_temporary_context"
    ENTITY_KEY: ClassVar[str] = "recommendation_entity_ids"
    REJECTED_KEY: ClassVar[str] = "recommendation_rejected_ids"
    INFERRED_KEY: ClassVar[str] = "recommendation_inferred_tags"
    MAX_HISTORY: ClassVar[int] = 100
    LAST_ACTIVE_KEY: ClassVar[str] = 'recommendation_last_active'
    FOCUS_KEY: ClassVar[str] = 'recommendation_focused_item_id'
    CANDIDATES_KEY: ClassVar[str] = 'recommendation_candidate_ids'
    SCHEMA_KEY: ClassVar[str] = 'recommendation_schema_version'
    REVISION_KEY: ClassVar[str] = 'recommendation_revision'
    SCHEMA_VERSION: ClassVar[int] = 6
    CONTEXTS_KEY: ClassVar[str] = 'recommendation_contexts'
    PENDING_BUDGET_KEY: ClassVar[str] = 'recommendation_pending_budget'
    FRAME_KEYS: ClassVar[tuple[str, ...]] = (
        STATE_KEY, SHOWN_KEY, SEARCH_KEY, LAST_RESULT_EMPTY_KEY, TEMP_CONTEXT_KEY,
        ENTITY_KEY, REJECTED_KEY, INFERRED_KEY, FOCUS_KEY, CANDIDATES_KEY,
        'last_question', 'last_recommendations', 'shown_recommendation_ids',
        'recommendation_required_tags',
    )

    def __init__(self, session: SessionBase) -> None:
        self._session: SessionBase = session

    def load_state(self) -> ConversationStatePayload:
        return cast(ConversationStatePayload, self._session.get(self.STATE_KEY, {}))

    @staticmethod
    def _owned_key(key: str) -> bool:
        return key.startswith('recommendation_') or key in {
            'last_question', 'last_recommendations', 'shown_recommendation_ids', 'gemini_calls',
        }

    def draft(self) -> SessionBase:
        draft = SessionBase()
        draft.update(deepcopy(dict(self._session)))
        state = ConversationSession(draft)
        version = draft.get(self.SCHEMA_KEY)
        if self.PENDING_BUDGET_KEY in draft:
            if version not in {5, self.SCHEMA_VERSION}:
                raise ValueError('Unsupported pending budget version')
            self.validate_pending_budget(draft[self.PENDING_BUDGET_KEY])
        if version is not None and (type(version) is not int or version not in {3, 4, 5, self.SCHEMA_VERSION}):
            if self.CONTEXTS_KEY in draft:
                raise ValueError('Unsupported scoped conversation version')
            state.reset()
        elif version in {4, 5}:
            if self.CONTEXTS_KEY in draft:
                self.validate_contexts(draft[self.CONTEXTS_KEY], schema_version=version)
            if self.SEARCH_KEY in draft:
                self.validate_search(draft[self.SEARCH_KEY], allow_soft=version >= 5)
            draft[self.SCHEMA_KEY] = self.SCHEMA_VERSION
        elif version == 3:
            # Legacy bounds belong to its one search, never an invented overall plan.
            draft[self.SCHEMA_KEY] = self.SCHEMA_VERSION
            state.contexts()['active']['legacy_unresolved'] = bool(state.load_constraints().excluded_tags)
        elif version is None and any(key.startswith('recommendation_') for key in draft.keys()):
            legacy = state.get_entity_ids()
            if len(legacy) == 1:
                state.set_focus(legacy[0])
            state.set_candidates(state.get_shown_ids() or state.get_last_recommendation_ids())
            draft[self.SCHEMA_KEY] = self.SCHEMA_VERSION
            state.contexts()['active']['legacy_unresolved'] = bool(state.load_constraints().excluded_tags)
        if self.SEARCH_KEY in draft:
            self.validate_search(draft[self.SEARCH_KEY])
        return draft

    @staticmethod
    def validate_pending_budget(data: object) -> None:
        if (not isinstance(data, dict) or set(data) != {'amount', 'context_id', 'expires_at'}
                or not isinstance(data['amount'], str) or len(data['amount']) > 32
                or type(data['context_id']) is not int or data['context_id'] <= 0
                or type(data['expires_at']) is not int or data['expires_at'] <= 0):
            raise ValueError('Invalid pending budget')
        try:
            BudgetConstraint(maximum=Decimal(data['amount']))
        except (ValueError, ArithmeticError) as error:
            raise ValueError('Invalid pending budget') from error

    def set_pending_budget(self, amount: Decimal) -> None:
        self._session[self.PENDING_BUDGET_KEY] = {
            'amount': str(amount), 'context_id': self.contexts()['active']['id'],
            'expires_at': int(time()) + min(300, getattr(settings, 'CHATBOT_DIALOG_IDLE_SECONDS', 1800)),
        }
        self.set_last_question('budget_scope')

    def clear_pending_budget(self) -> None:
        self._session.pop(self.PENDING_BUDGET_KEY, None)
        if self.get_last_question() == 'budget_scope':
            self.set_last_question(None)

    def pending_budget(self) -> Decimal | None:
        data = self._session.get(self.PENDING_BUDGET_KEY)
        if data is None:
            return None
        self.validate_pending_budget(data)
        if data['expires_at'] <= int(time()) or data['context_id'] != self.contexts()['active']['id']:
            self.clear_pending_budget()
            return None
        return Decimal(data['amount'])

    def projection(self) -> dict[str, object]:
        return {key: deepcopy(self._session[key]) for key in self.FRAME_KEYS if key in self._session}

    def clear_projection(self) -> None:
        for key in self.FRAME_KEYS:
            self._session.pop(key, None)

    def _frame(self, identifier: int) -> dict:
        return {'id': identifier, 'intent': 'UNKNOWN', 'kind': 'SEARCH',
                'category': self.load_constraints().category, 'focused_item_id': self.get_focus(),
                'constraints': self.load_constraints().to_dict(), 'projection': self.projection(),
                'updated_at': int(time()), 'item_excluded_tags': [], 'legacy_unresolved': False}

    def contexts(self) -> dict:
        stored = self._session.get(self.CONTEXTS_KEY)
        if stored is None:
            stored = {'active': self._frame(1), 'previous': [], 'next_id': 2,
                      'overall': {}, 'safety': {'excluded_tags': [], 'verification_required': False},
                      'plan': {'id': 1, 'entries': [], 'unresolved_roles': [], 'status': 'draft'},
                      'transition': {'action': 'NEW_REQUEST', 'reason_code': 'initial',
                                     'applied_constraint_ids': [], 'ignored_constraint_ids': []}}
            self._session[self.CONTEXTS_KEY] = stored
        self.validate_contexts(stored)
        return stored

    @classmethod
    def validate_contexts(cls, data: object, *, schema_version: int | None = None) -> None:
        """Validate untrusted persisted state before restoring any projection."""
        if schema_version is not None and (type(schema_version) is not int or schema_version not in {3, 4, 5, cls.SCHEMA_VERSION}):
            raise ValueError('Unsupported scoped conversation version')
        allow_soft = schema_version in {None, 5, cls.SCHEMA_VERSION}
        allow_plan = schema_version in {None, cls.SCHEMA_VERSION}
        if not isinstance(data, dict) or set(data) != {'active', 'previous', 'next_id', 'overall', 'safety', 'plan', 'transition'}:
            raise ValueError('Invalid conversation context')
        if type(data['next_id']) is not int or not 1 < data['next_id'] < 2 ** 53:
            raise ValueError('Invalid context version')
        if not isinstance(data['previous'], list) or len(data['previous']) > 4:
            raise ValueError('Invalid context history')
        ids = set()
        for frame in [data['active'], *data['previous']]:
            if not isinstance(frame, dict) or set(frame) != {'id', 'intent', 'kind', 'category', 'focused_item_id', 'constraints', 'projection', 'updated_at', 'item_excluded_tags', 'legacy_unresolved'}:
                raise ValueError('Invalid context frame')
            if type(frame['id']) is not int or not 0 < frame['id'] < data['next_id'] or frame['id'] in ids:
                raise ValueError('Invalid context identity')
            ids.add(frame['id'])
            if not isinstance(frame['intent'], str) or len(frame['intent']) > 64 or frame['kind'] not in {'SEARCH', 'ITEM', 'PLAN'}:
                raise ValueError('Invalid context intent')
            if frame['category'] is not None and (not isinstance(frame['category'], str) or len(frame['category']) > 100):
                raise ValueError('Invalid context category')
            if frame['focused_item_id'] is not None and (type(frame['focused_item_id']) is not int or frame['focused_item_id'] <= 0):
                raise ValueError('Invalid context focus')
            if type(frame['updated_at']) is not int or type(frame['legacy_unresolved']) is not bool:
                raise ValueError('Invalid context lifetime')
            if not isinstance(frame['projection'], dict) or set(frame['projection']) - set(cls.FRAME_KEYS):
                raise ValueError('Invalid context projection')
            if not isinstance(frame['constraints'], dict):
                raise ValueError('Invalid context constraints')
            cls.validate_search(frame['constraints'], allow_soft=allow_soft)
            for key, value in frame['projection'].items():
                if key == cls.SEARCH_KEY:
                    cls.validate_search(value, allow_soft=allow_soft)
                elif key in {cls.SHOWN_KEY, cls.CANDIDATES_KEY, cls.ENTITY_KEY, cls.REJECTED_KEY, 'last_recommendations', 'shown_recommendation_ids'}:
                    if not isinstance(value, list) or len(value) > cls.MAX_HISTORY or any(type(identifier) is not int or identifier <= 0 for identifier in value):
                        raise ValueError('Invalid context candidate IDs')
                elif key in {cls.INFERRED_KEY, 'recommendation_required_tags'}:
                    if not isinstance(value, list) or len(value) > 100 or any(not isinstance(tag, str) or len(tag) > 50 for tag in value):
                        raise ValueError('Invalid context tag IDs')
            SearchConstraints.from_dict(frame['constraints'])
            if not isinstance(frame['item_excluded_tags'], list) or len(frame['item_excluded_tags']) > 32 or any(not isinstance(tag, str) or len(tag) > 50 for tag in frame['item_excluded_tags']):
                raise ValueError('Invalid item restriction')
        safety, overall, plan, transition = (data[key] for key in ('safety', 'overall', 'plan', 'transition'))
        if not isinstance(safety, dict) or set(safety) != {'excluded_tags', 'verification_required'} or type(safety['verification_required']) is not bool:
            raise ValueError('Invalid safety restriction')
        if not isinstance(safety['excluded_tags'], list) or len(safety['excluded_tags']) > 32 or any(not isinstance(tag, str) or len(tag) > 50 for tag in safety['excluded_tags']):
            raise ValueError('Invalid safety tags')
        overall_keys = {'total_budget', 'per_person_budget', 'person_count', 'requested_categories', 'explicitly_declared', 'plan_id'}
        if allow_plan:
            overall_keys.add('category_budgets')
        if not isinstance(overall, dict) or set(overall) - overall_keys:
            raise ValueError('Invalid overall constraints')
        for key in ('total_budget', 'per_person_budget'):
            if key in overall:
                if not isinstance(overall[key], str):
                    raise ValueError('Invalid overall price')
                BudgetConstraint(maximum=Decimal(overall[key]))
        if 'person_count' in overall and (type(overall['person_count']) is not int or not 1 <= overall['person_count'] <= 99):
            raise ValueError('Invalid person count')
        budget_count = len(set(overall) & {'total_budget', 'per_person_budget'})
        if overall and (overall.get('explicitly_declared') is not True or type(overall.get('plan_id')) is not int or overall['plan_id'] <= 0
                        or (budget_count != 1 if not allow_plan else budget_count == 0 and not overall.get('category_budgets'))):
            raise ValueError('Invalid budget provenance')
        if 'category_budgets' in overall:
            allocations = overall['category_budgets']
            if not isinstance(allocations, dict) or not 1 <= len(allocations) <= 8:
                raise ValueError('Invalid category allocations')
            for role, amount in allocations.items():
                if not isinstance(role, str) or not 1 <= len(role) <= 100 or not isinstance(amount, str) or len(amount) > 32:
                    raise ValueError('Invalid category allocation')
                BudgetConstraint(maximum=Decimal(amount))
        if 'requested_categories' in overall and (not isinstance(overall['requested_categories'], list) or len(overall['requested_categories']) > 8 or any(not isinstance(role, str) or len(role) > 100 for role in overall['requested_categories'])):
            raise ValueError('Invalid requested roles')
        plan_keys = {'id', 'entries', 'unresolved_roles', 'status'}
        if not isinstance(plan, dict) or not plan_keys <= set(plan) or set(plan) - plan_keys - ({'scopes', 'serving_mode', 'role_quantities'} if allow_plan else set()) or type(plan['id']) is not int or plan['id'] <= 0 or plan['status'] != 'draft':
            raise ValueError('Invalid recommendation plan')
        if not isinstance(plan['entries'], list) or len(plan['entries']) > 8 or not isinstance(plan['unresolved_roles'], list) or len(plan['unresolved_roles']) > 8 or any(not isinstance(role, str) or len(role) > 100 for role in plan['unresolved_roles']):
            raise ValueError('Invalid plan size')
        for entry in plan['entries']:
            if not isinstance(entry, dict) or set(entry) != {'context_id', 'menu_id', 'quantity'} or any(type(entry[key]) is not int or entry[key] <= 0 for key in entry) or entry['quantity'] > 99:
                raise ValueError('Invalid plan entry')
        if plan.get('serving_mode', 'unspecified') not in {'unspecified', 'shared', 'individual'}:
            raise ValueError('Invalid serving mode')
        role_quantities = plan.get('role_quantities', {})
        if not isinstance(role_quantities, dict) or len(role_quantities) > 8 or any(
                not isinstance(role, str) or not 1 <= len(role) <= 100 or type(quantity) is not int or not 1 <= quantity <= 99
                for role, quantity in role_quantities.items()):
            raise ValueError('Invalid role quantities')
        scopes = plan.get('scopes', {})
        if not isinstance(scopes, dict) or len(scopes) > 8:
            raise ValueError('Invalid plan scopes')
        owners = {str(entry['context_id']) for entry in plan['entries']}
        for owner, scope in scopes.items():
            if owner not in owners or not owner.isdecimal() or not 0 < int(owner) < data['next_id'] or not isinstance(scope, dict) or set(scope) != {'constraints', 'focused_item_id', 'item_excluded_tags'}:
                raise ValueError('Invalid plan scope owner')
            cls.validate_search(scope['constraints'])
            if scope['focused_item_id'] is not None and (type(scope['focused_item_id']) is not int or scope['focused_item_id'] <= 0):
                raise ValueError('Invalid plan scope focus')
            if not isinstance(scope['item_excluded_tags'], list) or len(scope['item_excluded_tags']) > 32 or any(not isinstance(tag, str) or len(tag) > 50 for tag in scope['item_excluded_tags']):
                raise ValueError('Invalid plan scope exclusions')
        actions = {'CONTINUE_CONTEXT', 'SWITCH_CONTEXT', 'NEW_REQUEST', 'ADD_TO_CONTEXT', 'CORRECT_PREVIOUS', 'REFER_TO_PREVIOUS', 'CLARIFY'}
        if not isinstance(transition, dict) or set(transition) != {'action', 'reason_code', 'applied_constraint_ids', 'ignored_constraint_ids'} or transition['action'] not in actions:
            raise ValueError('Invalid context action')
        if not isinstance(transition['reason_code'], str) or len(transition['reason_code']) > 64 or any(not isinstance(transition[key], list) or len(transition[key]) > 512 or any(not isinstance(value, str) or len(value) > 100 for value in transition[key]) for key in ('applied_constraint_ids', 'ignored_constraint_ids')):
            raise ValueError('Invalid constraint references')

    @staticmethod
    def validate_search(data: object, *, allow_soft: bool = True) -> None:
        allowed = {'required_tags', 'excluded_tags', 'category', 'max_price', 'moods', 'budget'}
        if allow_soft:
            allowed.add('soft_target')
        if not isinstance(data, dict) or set(data) - allowed:
            raise ValueError('Invalid scoped search')
        for key in ('required_tags', 'excluded_tags', 'moods'):
            value = data.get(key, [])
            if not isinstance(value, list) or len(value) > 100 or any(not isinstance(tag, str) or len(tag) > 50 for tag in value):
                raise ValueError('Invalid scoped tags')
        category = data.get('category')
        if category is not None and (not isinstance(category, str) or len(category) > 100):
            raise ValueError('Invalid scoped category')
        price = data.get('max_price')
        if price is not None and (type(price) is not int or not 0 <= price <= 1000000):
            raise ValueError('Invalid scoped price')
        if 'budget' in data:
            BudgetConstraint.from_dict(data['budget'])
        if 'soft_target' in data:
            if not isinstance(data['soft_target'], str) or len(data['soft_target']) > 32:
                raise ValueError('Invalid soft target')
            try:
                SearchConstraints.from_dict(data)
            except (ValueError, ArithmeticError) as error:
                raise ValueError('Invalid soft target') from error

    def archive_context(self, category: str | None, *, item: bool = False) -> None:
        data = self.contexts()
        if data['plan']['entries']:
            self.commit_plan(data['plan']['entries'])
        old = deepcopy(data['active'])
        old.update(projection=self.projection(), constraints=self.load_constraints().to_dict(),
                   focused_item_id=self.get_focus(), updated_at=int(time()))
        if old['projection']:
            data['previous'] = (data['previous'] + [old])[-4:]
        self.clear_projection()
        data['active'] = self._frame(data['next_id'])
        data['next_id'] += 1
        data['active'].update(category=category, kind='ITEM' if item else 'SEARCH')

    def restore_context(self, reference: str | None, *, menu_id: int | None = None) -> bool:
        data = self.contexts()
        if data['plan']['entries']:
            self.commit_plan(data['plan']['entries'])
        lifetime = getattr(settings, 'CHATBOT_DIALOG_IDLE_SECONDS', 1800)
        candidates = [frame for frame in data['previous'] if int(time()) - frame['updated_at'] < lifetime
                      and (reference in {None, 'first'} or (frame['category'] or '').casefold() == reference.casefold())
                      and (menu_id is None or frame['focused_item_id'] == menu_id
                           or menu_id in frame['projection'].get('last_recommendations', [])
                           or menu_id in frame['projection'].get(self.CANDIDATES_KEY, []))]
        if not candidates:
            return False
        chosen = candidates[0] if reference == 'first' else candidates[-1]
        if reference == 'first' and chosen['id'] != 1:
            return False
        old = deepcopy(data['active'])
        old.update(projection=self.projection(), constraints=self.load_constraints().to_dict(), focused_item_id=self.get_focus())
        data['previous'] = ([frame for frame in data['previous'] if frame['id'] != chosen['id']] + [old])[-4:]
        self.clear_projection()
        self._session.update(deepcopy(chosen['projection']))
        data['active'] = deepcopy(chosen)
        return True

    def global_exclusions(self) -> set[str]:
        return set(self.contexts()['safety']['excluded_tags'])

    def commit_plan(self, entries: list[dict[str, int]], *, scopes: dict | None = None) -> None:
        """Retain only compact owned constraints, separate from conversation archives."""
        data = self.contexts()
        frames = {frame['id']: frame for frame in [data['active'], *data['previous']]}
        old = {**data['plan'].get('scopes', {}), **(scopes or {})}
        scopes = {}
        for entry in entries:
            owner = str(entry['context_id'])
            frame = frames.get(entry['context_id'])
            if frame is not None:
                active = frame['id'] == data['active']['id']
                scopes[owner] = {
                    'constraints': self.load_constraints().to_dict() if active else deepcopy(frame['constraints']),
                    'focused_item_id': self.get_focus() if active else frame['focused_item_id'],
                    'item_excluded_tags': list(frame['item_excluded_tags']),
                }
            elif owner in old:
                scopes[owner] = deepcopy(old[owner])
        data['plan']['entries'] = deepcopy(entries)
        data['plan']['scopes'] = scopes

    def finish_context(self, action: str, intent: str | None) -> None:
        data = self.contexts()
        frame = data['active']
        frame.update(intent=intent or 'UNKNOWN', constraints=self.load_constraints().to_dict(),
                     projection=self.projection(), focused_item_id=self.get_focus(), updated_at=int(time()))
        frame['category'] = self.load_constraints().category or frame['category']
        def identifiers(context: dict) -> list[str]:
            search = context['constraints']
            result = [f"context:{context['id']}:budget"] if search.get('budget') or search.get('max_price') is not None else []
            result += [f"context:{context['id']}:exclude:{tag}" for tag in search.get('excluded_tags', [])]
            if search.get('category'):
                result.append(f"context:{context['id']}:category")
            result += [f"context:{context['id']}:require:{tag}" for tag in search.get('required_tags', [])]
            return result
        applied = identifiers(frame)
        if data['overall']:
            applied.append('overall:plan')
        applied += ['safety:' + tag for tag in data['safety']['excluded_tags']]
        data['transition'] = {'action': action, 'reason_code': action.casefold(),
                              'applied_constraint_ids': applied,
                              'ignored_constraint_ids': [value for previous in data['previous'] for value in identifiers(previous)]}
        self._session[self.SCHEMA_KEY] = self.SCHEMA_VERSION
        self.validate_contexts(data)

    def preserve_usage(self, draft: SessionBase) -> None:
        old = self._session.get(self.GEMINI_CALLS_KEY, 0)
        new = draft.get(self.GEMINI_CALLS_KEY, 0)
        if type(new) is int and new >= 0 and (type(old) is not int or new > old):
            self._session[self.GEMINI_CALLS_KEY] = new

    def commit(self, draft: SessionBase) -> None:
        """Commit one validated turn; revision is metadata, not distributed CAS."""
        keys = {key for key in set(self._session.keys()) | set(draft.keys()) if self._owned_key(key)}
        changed = any(self._session.get(key) != draft.get(key) or (key in self._session) != (key in draft) for key in keys)
        if not changed:
            return
        for key in keys:
            if key in draft:
                self._session[key] = draft[key]
            else:
                self._session.pop(key, None)
        revision = self._session.get(self.REVISION_KEY, 0)
        self._session[self.REVISION_KEY] = (revision if type(revision) is int and revision >= 0 else 0) + 1
        self._session[self.SCHEMA_KEY] = self.SCHEMA_VERSION

    def get_focus(self) -> int | None:
        value = self._session.get(self.FOCUS_KEY)
        if type(value) is int and value > 0:
            return value
        legacy = self.get_entity_ids()
        return legacy[0] if len(legacy) == 1 else None

    def set_focus(self, identifier: int | None) -> None:
        if identifier is None:
            self._session.pop(self.FOCUS_KEY, None)
            self._session.pop(self.ENTITY_KEY, None)
        elif type(identifier) is int and identifier > 0:
            self._session[self.FOCUS_KEY] = identifier
            self._session[self.ENTITY_KEY] = [identifier]  # bounded legacy compatibility mirror
        else:
            raise ValueError('Invalid focus ID')

    def get_candidates(self) -> list[int]:
        return self._bounded_ids(self._session.get(self.CANDIDATES_KEY, []))

    def set_candidates(self, identifiers: list[int]) -> None:
        self._session[self.CANDIDATES_KEY] = self._bounded_ids(identifiers)

    def expire_dialog(self, *, touch: bool = True) -> None:
        now = int(time())
        previous = self._session.get(self.LAST_ACTIVE_KEY)
        lifetime = getattr(settings, 'CHATBOT_DIALOG_IDLE_SECONDS', 1800)
        if type(previous) is int and now - previous >= lifetime:
            self.reset()
        if touch:
            self._session[self.LAST_ACTIVE_KEY] = now

    def load_preferences(self) -> Preferences:
        return Preferences.from_dict(self.load_state())

    def load_constraints(self) -> SearchConstraints:
        stored = self._session.get(self.SEARCH_KEY)
        if isinstance(stored, dict):
            return SearchConstraints.from_dict(stored)
        preferences = self.load_preferences()
        return SearchConstraints(
            required_tags=frozenset(self._session.get("recommendation_required_tags", [])),
            category=preferences.category,
            max_price=preferences.max_price,
            moods=frozenset(preferences.moods),
        )

    def save_preferences(
        self, preferences: Preferences, state: str, follow_up: str | None = None,
    ) -> None:
        payload: ConversationStatePayload = {
            **preferences.to_dict(state=state, follow_up=follow_up),
            "max_price": None,
            "category": None,
            "last_question": self.get_last_question(),
            "last_recommendations": self.get_last_recommendation_ids(),
            "shown_recommendation_ids": self._session.get("shown_recommendation_ids", []),
        }
        self._session[self.STATE_KEY] = payload
        self._session.modified = True

    def save_search(
        self, constraints: SearchConstraints, *, update_required_tags: bool = False,
    ) -> None:
        self._session[self.SEARCH_KEY] = constraints.to_dict()
        if update_required_tags:
            self._session["recommendation_required_tags"] = sorted(constraints.required_tags)

    def get_last_question(self) -> str | None:
        return self._session.get("last_question")

    def set_last_question(self, question: str | None) -> None:
        self._session["last_question"] = question
        stored = self.load_state()
        if stored:
            self._session[self.STATE_KEY] = {**stored, "last_question": question}

    def get_shown_ids(self) -> list[int]:
        return self._session.get(self.SHOWN_KEY, [])

    def get_last_recommendation_ids(self) -> list[int]:
        return self._session.get("last_recommendations", [])

    def get_rejected_ids(self) -> list[int]:
        focused = self.get_focus()
        return [focused] if focused is not None else list(self.get_last_recommendation_ids())

    def last_result_empty(self) -> bool:
        return self._session.get(self.LAST_RESULT_EMPTY_KEY, False)

    @classmethod
    def _bounded_ids(cls, values: object) -> list[int]:
        if not isinstance(values, (list, tuple)):
            return []
        return list(dict.fromkeys(value for value in values if type(value) is int and value > 0))[-cls.MAX_HISTORY:]

    def get_entity_ids(self) -> list[int]:
        return self._bounded_ids(self._session.get(self.ENTITY_KEY, []))

    def set_entity_ids(self, ids: list[int]) -> None:
        if ids:
            self._session[self.ENTITY_KEY] = self._bounded_ids(ids)
            if len(self._session[self.ENTITY_KEY]) == 1:
                self._session[self.FOCUS_KEY] = self._session[self.ENTITY_KEY][0]
            else:
                self._session.pop(self.FOCUS_KEY, None)
        else:
            self._session.pop(self.ENTITY_KEY, None)
            self._session.pop(self.FOCUS_KEY, None)

    def get_explicit_rejections(self) -> list[int]:
        return self._bounded_ids(self._session.get(self.REJECTED_KEY, []))

    def remember_rejected(self, ids: list[int]) -> None:
        self._session[self.REJECTED_KEY] = self._bounded_ids(self.get_explicit_rejections() + ids)

    def allow_requested(self, ids: list[int]) -> None:
        self._session[self.REJECTED_KEY] = [value for value in self.get_explicit_rejections() if value not in ids]

    def record_recommendations(
        self, ids: list[int], *, shown_ids: list[int] | None = None,
    ) -> None:
        """None leaves shown history unchanged, as an empty catalog answer does."""
        self._session["last_recommendations"] = self._bounded_ids(ids)
        if shown_ids is not None:
            self._session[self.SHOWN_KEY] = self._bounded_ids(shown_ids)
            self._session["shown_recommendation_ids"] = self._bounded_ids(shown_ids)
        self._session[self.LAST_RESULT_EMPTY_KEY] = not ids
        self._session.modified = True

    def consume_gemini_call(self, maximum: int) -> bool:
        maximum = max(0, int(maximum))
        calls = int(self._session.get(self.GEMINI_CALLS_KEY, 0))
        if calls >= maximum:
            return False
        self._session[self.GEMINI_CALLS_KEY] = calls + 1
        self._session.modified = True
        return True

    def advance_context(self, context: UserContext, *, explicit_food: bool) -> bool:
        """Only coarse physical/situation labels survive up to two further turns."""
        old = self._session.get(self.TEMP_CONTEXT_KEY, {})
        if not isinstance(old, dict):
            old = {}
        remaining = old.get("remaining_turns", 0)
        remaining = remaining if type(remaining) is int else 0
        now = int(time())
        expires = old.get("expires_at", 0)
        expires = expires if type(expires) is int else 0
        clear = bool(context.cleared_physical) or (bool(old) and (remaining <= 1 or expires <= now)) or (explicit_food and not context.physical)
        if context.physical or context.situations:
            if context.physical and sorted(context.physical) != old.get("physical", []):
                clear = True
            if context.situations and not context.physical and old.get("physical"):
                clear = True
            self._session[self.TEMP_CONTEXT_KEY] = {
                "physical": sorted(context.physical), "situations": sorted(context.situations),
                "remaining_turns": 2,
                "expires_at": now + 300,
            }
        elif old and not clear:
            self._session[self.TEMP_CONTEXT_KEY] = {**old, "remaining_turns": remaining - 1}
        else:
            self._session.pop(self.TEMP_CONTEXT_KEY, None)
        return clear

    def reset(self) -> None:
        for key in (
            self.STATE_KEY, self.SHOWN_KEY, "recommendation_context", self.TEMP_CONTEXT_KEY,
            "shown_recommendation_ids", "last_recommendations", "last_question",
            "recommendation_required_tags", self.SEARCH_KEY,
            self.LAST_RESULT_EMPTY_KEY,
            "recommendation_response_templates",
            self.ENTITY_KEY, self.REJECTED_KEY, self.INFERRED_KEY,
            self.LAST_ACTIVE_KEY,
            self.FOCUS_KEY, self.CANDIDATES_KEY, self.SCHEMA_KEY,
            self.CONTEXTS_KEY,
            self.PENDING_BUDGET_KEY,
        ):
            self._session.pop(key, None)
        self._session.modified = True
