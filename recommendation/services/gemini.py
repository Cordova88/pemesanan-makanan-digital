import os
from time import perf_counter
from typing import override

from django.conf import settings
import httpx
from google import genai
from google.genai import errors, types

from .text_generator import TextGenerator
from .security import UsageGuard
from .telemetry import ProviderEvent, provider_event, provider_failure_event


class GeminiClient(TextGenerator):
    def __init__(self) -> None:
        self.client: genai.Client | None = None
        self.last_event: ProviderEvent | None = None
        api_key = getattr(settings, 'GEMINI_API_KEY', '') or os.getenv('GEMINI_API_KEY')
        if getattr(settings, 'GEMINI_ENABLED', False) and api_key:
            self.client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=15000, retry_options=types.HttpRetryOptions(attempts=1)),
            )

    @property
    def available(self) -> bool:
        return bool(getattr(settings, 'GEMINI_ENABLED', False) and self.client is not None)

    @staticmethod
    def _failure_metadata(exc: Exception) -> tuple[str, int | None]:
        if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
            return 'timeout', None
        if isinstance(exc, httpx.TransportError):
            return 'transport', None
        if isinstance(exc, errors.APIError):
            status = exc.code if type(exc.code) is int and 100 <= exc.code <= 599 else None
            category = ('authentication' if status in {401, 403} else
                        'rate_limited' if status == 429 else
                        'upstream' if status is not None and status >= 500 else
                        'invalid_request' if status == 400 else 'api_error')
            return category, status
        return 'unexpected', None

    @override
    def generate(self, prompt: str) -> str | None:
        model = settings.GEMINI_MODEL
        if not getattr(settings, 'GEMINI_ENABLED', False):
            self.last_event = provider_event(model, 'disabled', 0)
            return None
        if self.client is None:
            self.last_event = provider_event(model, 'unconfigured', 0)
            return None
        try:
            valid_prompt = isinstance(prompt, str) and len(prompt.encode('utf-8')) <= 16000
        except UnicodeError:
            valid_prompt = False
        if not valid_prompt:
            self.last_event = provider_event(model, 'input_rejected', 0)
            return None
        guard = UsageGuard()
        if not guard.allow_provider():
            self.last_event = provider_event(model, 'guard_unavailable' if guard.unavailable else 'quota_exhausted', 0)
            return None
        started = perf_counter()
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(max_output_tokens=512),
            )
            text = response.text or None
            if text is not None and (not isinstance(text, str) or len(text) > 16000):
                text = None
            self.last_event = provider_event(model, 'success' if text else 'empty_or_rejected', (perf_counter() - started) * 1000, getattr(response, 'usage_metadata', None))
            return text
        except Exception as exc:
            category, status = self._failure_metadata(exc)
            outcome = 'TimeoutError' if category == 'timeout' else 'provider_error'
            self.last_event = provider_event(model, outcome, (perf_counter() - started) * 1000, failed=True)
            provider_failure_event(category, status)
            return None
