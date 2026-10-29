"""Authoritative chatbot-only state, with optimistic SQL compare-and-swap.

Uses the existing django_session table with a separate HMAC-derived key and
signing salt. Auth/cart sessions keep a compatibility mirror, never authority.
"""

from copy import deepcopy
from datetime import timedelta
import json
from typing import ClassVar

from django.contrib.sessions.backends.base import SessionBase
from django.contrib.sessions.models import Session
from django.core import signing
from django.utils import timezone

from .conversation_session import ConversationSession
from .security import UsageGuard


class ConversationConflict(Exception):
    def __init__(self, revision: int) -> None:
        super().__init__('Conversation revision conflict')
        self.revision: int = revision


class ConversationStoreUnavailable(Exception):
    pass


class ConversationStore:
    SALT: ClassVar[str] = 'rasakita.chat-state.v4'
    PREFIX: ClassVar[str] = 'rkchatv4'
    MAX_BYTES: ClassVar[int] = 32768
    RETENTION_SECONDS: ClassVar[int] = 86400

    def __init__(
        self,
        identity: str,
        legacy: SessionBase,
        expected_revision: int | None = None,
    ) -> None:
        self.key: str = self.PREFIX + UsageGuard.identity('chat-state:' + identity)[:32]
        self.session: SessionBase = SessionBase()
        self._usage_recorded: bool = False
        now = timezone.now()
        initial = self._owned(legacy)
        imported = SessionBase()
        imported.update(initial)
        # A compatibility mirror cannot resurrect an idle-expired conversation.
        ConversationSession(imported).expire_dialog()
        row, _ = Session.objects.get_or_create(
            session_key=self.key,
            defaults={
                'session_data': self._encode(self._owned(imported)),
                'expire_date': now + timedelta(seconds=self.RETENTION_SECONDS),
            },
        )

        if row.expire_date <= now:
            expired = self._decode(row.session_data)
            empty = SessionBase()
            empty[ConversationSession.GEMINI_CALLS_KEY] = max(
                self._usage(expired),
                self._usage(initial),
            )
            empty[ConversationSession.REVISION_KEY] = self._revision(expired) + 1
            replacement = self._encode(dict(empty))
            Session.objects.filter(
                session_key=self.key, session_data=row.session_data
            ).update(
                session_data=replacement,
                expire_date=now + timedelta(seconds=self.RETENTION_SECONDS),
            )
            row = Session.objects.get(session_key=self.key)

        self._encoded: str = row.session_data
        state = self._decode(self._encoded)
        self.session.update(deepcopy(state))
        self.base_revision: int = self._revision(state)
        self._base_usage: int = self._usage(state)

        if expected_revision is not None and expected_revision != self.base_revision:
            raise ConversationConflict(self.base_revision)

    @staticmethod
    def _owned(session: SessionBase) -> dict[str, object]:
        return {
            key: deepcopy(session[key])
            for key in session.keys()
            if isinstance(key, str) and ConversationSession._owned_key(key)
        }

    @staticmethod
    def _revision(state: dict[str, object]) -> int:
        value = state.get(ConversationSession.REVISION_KEY, 0)

        if type(value) is not int or not 0 <= value < 2**53:
            raise ConversationStoreUnavailable()

        return value

    @staticmethod
    def _usage(state: dict[str, object]) -> int:
        value = state.get(ConversationSession.GEMINI_CALLS_KEY, 0)

        return value if type(value) is int and value >= 0 else 0

    @classmethod
    def _encode(cls, state: dict[str, object]) -> str:
        try:
            cls._revision(state)

            if (
                len(json.dumps(state, ensure_ascii=False, allow_nan=False).encode('utf-8'))
                > cls.MAX_BYTES
            ):
                raise ConversationStoreUnavailable()

            encoded = signing.dumps({'schema': 2, 'state': state}, salt=cls.SALT)

            if len(encoded) > cls.MAX_BYTES * 2:
                raise ConversationStoreUnavailable()

            return encoded
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ConversationStoreUnavailable() from None

    @classmethod
    def _decode(cls, encoded: str) -> dict[str, object]:
        try:
            if len(encoded) > cls.MAX_BYTES * 2:
                raise ConversationStoreUnavailable()

            data = signing.loads(encoded, salt=cls.SALT)

            if (
                type(data) is not dict
                or set(data) != {'schema', 'state'}
                or type(data['schema']) is not int
                or data['schema'] != 2
                or type(data['state']) is not dict
            ):
                raise ConversationStoreUnavailable()

            state = {
                key: value
                for key, value in data['state'].items()
                if isinstance(key, str) and ConversationSession._owned_key(key)
            }
            cls._revision(state)

            if (
                len(json.dumps(state, ensure_ascii=False, allow_nan=False).encode('utf-8'))
                > cls.MAX_BYTES
            ):
                raise ConversationStoreUnavailable()

            return state
        except (signing.BadSignature, ValueError, TypeError, UnicodeError, RecursionError):
            raise ConversationStoreUnavailable() from None

    @property
    def revision(self) -> int:
        return self._revision(self._owned(self.session))

    def commit(self) -> int:
        state = self._owned(self.session)
        state[ConversationSession.REVISION_KEY] = self.base_revision + 1
        encoded = self._encode(state)
        changed = Session.objects.filter(
            session_key=self.key,
            session_data=self._encoded,
            expire_date__gt=timezone.now(),
        ).update(
            session_data=encoded,
            expire_date=timezone.now() + timedelta(seconds=self.RETENTION_SECONDS),
        )

        if changed != 1:
            self.preserve_usage()
            row = Session.objects.filter(session_key=self.key).first()
            current = self._revision(self._decode(row.session_data)) if row is not None else 0

            raise ConversationConflict(current)

        self.session[ConversationSession.REVISION_KEY] = self.base_revision + 1
        self._usage_recorded = True

        return self.base_revision + 1

    def preserve_usage(self) -> None:
        """Charge attempts from a losing/failed turn, never its business delta."""

        if self._usage_recorded:
            return

        delta = max(0, self._usage(self._owned(self.session)) - self._base_usage)

        if delta == 0:
            self._usage_recorded = True

            return

        for _ in range(3):
            row = Session.objects.filter(
                session_key=self.key, expire_date__gt=timezone.now()
            ).first()

            if row is None:
                raise ConversationStoreUnavailable()

            state = self._decode(row.session_data)
            state[ConversationSession.GEMINI_CALLS_KEY] = self._usage(state) + delta
            state[ConversationSession.REVISION_KEY] = self._revision(state) + 1

            if (
                Session.objects.filter(
                    session_key=self.key, session_data=row.session_data
                ).update(session_data=self._encode(state))
                == 1
            ):
                self._usage_recorded = True

                return

        raise ConversationStoreUnavailable()

    def mirror(self, target: SessionBase, *, enabled: bool = True) -> None:
        state = self._owned(self.session) if enabled else {}

        for key in list(target.keys()):
            if isinstance(key, str) and ConversationSession._owned_key(key) and key not in state:
                target.pop(key, None)

        target.update(state)
