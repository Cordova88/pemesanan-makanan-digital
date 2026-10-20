"""Bounded chat input and cache-backed quotas, without raw identity logging."""
import json
import time
from contextvars import ContextVar
from hashlib import sha256
import hmac
from typing import ClassVar
from uuid import uuid4

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.base import BaseCache
from django.http import HttpRequest

request_context: ContextVar[dict[str, str]] = ContextVar('chatbot_request_context', default={})


class ChatInputError(ValueError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status: int = status


class ChatInput:
    MAX_BYTES: ClassVar[int] = 8192
    MAX_MESSAGE: ClassVar[int] = 500

    def __init__(self, message: str, action: str = '', revision: int | None = None) -> None:
        self.message: str = message
        self.action: str = action
        self.revision: int | None = revision

    @classmethod
    def from_request(cls, request: HttpRequest) -> 'ChatInput':
        if request.content_type != 'application/json':
            raise ChatInputError(415, 'Gunakan format JSON.')
        length = request.META.get('CONTENT_LENGTH', '')
        try:
            if length and int(length) > cls.MAX_BYTES:
                raise ChatInputError(413, 'Pesan terlalu besar.')
        except (ValueError, TypeError) as error:
            if isinstance(error, ChatInputError):
                raise
            raise ChatInputError(400, 'Pesan tidak valid.') from None
        raw = request.read(cls.MAX_BYTES + 1)
        if len(raw) > cls.MAX_BYTES:
            raise ChatInputError(413, 'Pesan terlalu besar.')
        try:
            body = json.loads(raw.decode('utf-8'), object_pairs_hook=cls._unique_object)
        except (ValueError, UnicodeError, RecursionError):
            raise ChatInputError(400, 'Pesan tidak valid.') from None
        if not isinstance(body, dict) or set(body) - {'message', 'action', 'revision'}:
            raise ChatInputError(400, 'Pesan tidak valid.')
        message = body.get('message', '')
        action = body.get('action', '')
        revision = body.get('revision')
        if 'revision' in body and (type(revision) is not int or not 0 <= revision < 2 ** 53):
            raise ChatInputError(400, 'Versi percakapan tidak valid.')
        if not isinstance(message, str) or not isinstance(action, str) or action not in {'', 'more', 'reset'}:
            raise ChatInputError(400, 'Pesan tidak valid.')
        if len(message) > cls.MAX_MESSAGE:
            raise ChatInputError(413, 'Pesan maksimal 500 karakter.')
        if any(ord(character) < 32 and character not in '\t\r\n' for character in message):
            raise ChatInputError(400, 'Pesan tidak valid.')
        if any(0xD800 <= ord(character) <= 0xDFFF for character in message):
            raise ChatInputError(400, 'Pesan tidak valid.')
        return cls(message.strip(), action, revision)

    @staticmethod
    def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result


class UsageGuard:
    SHARED: ClassVar[frozenset[str]] = frozenset({
        'django.core.cache.backends.redis.RedisCache',
        'django.core.cache.backends.memcached.PyMemcacheCache',
        'django.core.cache.backends.memcached.PyLibMCCache',
    })

    def __init__(self, cache: BaseCache | None = None) -> None:
        self.cache: BaseCache | None = cache
        self.unavailable: bool = False
        if self.cache is None:
            try:
                alias = getattr(settings, 'CHATBOT_CACHE_ALIAS', 'default')
                backend = settings.CACHES[alias]['BACKEND']
                shared_required = getattr(settings, 'CHATBOT_REQUIRE_SHARED_CACHE', not settings.DEBUG)
                if backend not in self.SHARED and (shared_required or backend != 'django.core.cache.backends.locmem.LocMemCache'):
                    self.unavailable = True
                else:
                    self.cache = caches[alias]
            except Exception:
                self.unavailable = True

    @staticmethod
    def identity(value: str) -> str:
        return hmac.new(settings.SECRET_KEY.encode('utf-8'), value.encode('utf-8'), sha256).hexdigest()

    def consume(self, bucket: str, limit: int, seconds: int) -> bool:
        if self.unavailable or self.cache is None or type(limit) is not int or limit <= 0 or type(seconds) is not int or seconds <= 0:
            return False
        key = f'chatbot:v2:{bucket}:{int(time.time()) // seconds}'
        try:
            count = 1 if self.cache.add(key, 1, timeout=seconds + 5) else self.cache.incr(key)
            return type(count) is int and count <= limit
        except Exception:
            self.unavailable = True
            return False

    def allow_request(self, session_id: str, client_id: str) -> bool:
        return (
            self.consume('request:global', getattr(settings, 'CHATBOT_REQUESTS_GLOBAL_PER_MINUTE', 600), 60)
            and self.consume('request:client:' + client_id, getattr(settings, 'CHATBOT_REQUESTS_CLIENT_PER_MINUTE', 120), 60)
            and self.consume('request:session:' + session_id, getattr(settings, 'CHATBOT_REQUESTS_SESSION_PER_MINUTE', 60), 60)
        )

    def allow_provider(self) -> bool:
        context = request_context.get()
        if not self.consume('provider:global', getattr(settings, 'GEMINI_GLOBAL_CALLS_PER_DAY', 100), 86400):
            return False
        if context.get('client') and not self.consume('provider:client:' + context['client'], getattr(settings, 'GEMINI_CLIENT_CALLS_PER_DAY', 20), 86400):
            return False
        if context.get('session') and not self.consume('provider:session:' + context['session'], settings.GEMINI_MAX_CALLS_PER_SESSION, 86400):
            return False
        return True

    def snapshot(self) -> dict[str, object]:
        counts: dict[str, object] = {'request_attempts_current_minute': None, 'provider_budget_attempts_current_utc_day': None, 'estimated_cost': None, 'guard_available': not self.unavailable}
        if self.cache is None or self.unavailable:
            return counts
        try:
            for field, bucket, seconds in (
                ('request_attempts_current_minute', 'request:global', 60),
                ('provider_budget_attempts_current_utc_day', 'provider:global', 86400),
            ):
                value = self.cache.get(f'chatbot:v2:{bucket}:{int(time.time()) // seconds}', 0)
                counts[field] = value if type(value) is int and value >= 0 else None
        except Exception:
            counts['guard_available'] = False
        return counts


def correlation_id() -> str:
    return request_context.get().get('request_id') or uuid4().hex
