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
                http_options=types.HttpOptions(
                    timeout=30000, retry_options=types.HttpRetryOptions(attempts=1)
                ),
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
            category = (
                'authentication'
                if status in {401, 403}
                else (
                    'rate_limited'
                    if status == 429
                    else (
                        'upstream'
                        if status is not None and status >= 500
                        else 'invalid_request' if status == 400 else 'api_error'
                    )
                )
            )

            return category, status

        return 'unexpected', None

    @override
    def generate(self, prompt: str) -> str | None:
        return self._generate(prompt, structured_ranking=False)

    @override
    def generate_ranking(self, prompt: str) -> str | None:
        # Opt in only after checking the deployed model. Never retry without schema.
        structured = getattr(settings, 'CHATBOT_RANKING_STRUCTURED_OUTPUT_ENABLED', False)

        return self._generate(prompt, structured_ranking=structured)

    @staticmethod
    def _ranking_schema() -> dict[str, object]:
        """Formatting aid only; eligibility and strict validation stay in the backend."""

        return {
            'type': 'object',
            'properties': {
                'ranked_candidates': {
                    'type': 'array',
                    'minItems': 1,
                    'maxItems': 8,
                    'items': {
                        'type': 'object',
                        'properties': {
                            'id': {'type': 'integer'},
                            'score': {'type': 'number', 'minimum': 0, 'maximum': 1},
                        },
                        'required': ['id', 'score'],
                        'additionalProperties': False,
                    },
                },
            },
            'required': ['ranked_candidates'],
            'additionalProperties': False,
        }

    def _generate(self, prompt: str, *, structured_ranking: bool) -> str | None:
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

        if not self._allow_provider(model):
            return None

        started = perf_counter()

        try:
            config = types.GenerateContentConfig(max_output_tokens=512)

            if structured_ranking:
                config.response_mime_type = 'application/json'
                config.response_json_schema = self._ranking_schema()

            response = self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
            text = response.text or None

            if text is not None and (not isinstance(text, str) or len(text) > 16000):
                text = None

            self.last_event = provider_event(
                model,
                'success' if text else 'empty_or_rejected',
                (perf_counter() - started) * 1000,
                getattr(response, 'usage_metadata', None),
            )

            return text
        except Exception as exc:
            category, status = self._failure_metadata(exc)
            outcome = 'TimeoutError' if category == 'timeout' else 'provider_error'
            self.last_event = provider_event(
                model, outcome, (perf_counter() - started) * 1000, failed=True
            )
            provider_failure_event(category, status)

            return None

    def _allow_provider(self, model: str) -> bool:
        """Apply shared daily accounting to every SDK dispatch, including tool turns."""
        guard = UsageGuard()
        if guard.allow_provider():
            return True
        self.last_event = provider_event(
            model, 'guard_unavailable' if guard.unavailable else 'quota_exhausted', 0
        )
        return False

    def converse(
        self,
        message: str,
        system_instruction: str,
        tool_declarations: list,
        tool_handler,
        before_request,
        max_iterations: int = 4,
    ) -> tuple[str | None, list]:
        if self.client is None or not getattr(settings, 'GEMINI_ENABLED', False):
            return None, []

        model = settings.GEMINI_MODEL
        contents = [
            types.Content(
                role="user",
                parts=[types.Part(text=message)],
            )
        ]
        tool = types.Tool(function_declarations=tool_declarations)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[tool],
            temperature=0.7,
            max_output_tokens=600,
        )
        tool_results = []
        for _ in range(max(1, max_iterations)):
            if before_request and not before_request():
                return None, tool_results
            if not self._allow_provider(model):
                return None, tool_results
            started = perf_counter()
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
            except Exception as exc:
                category, status = self._failure_metadata(exc)
                self.last_event = provider_event(
                    model,
                    'TimeoutError' if category == 'timeout' else 'provider_error',
                    (perf_counter() - started) * 1000,
                    failed=True,
                )
                provider_failure_event(category, status)
                return None, tool_results

            candidate = (response.candidates or [None])[0]
            content = candidate.content if candidate else None
            # Record each SDK response before tools run or another turn can replace it.
            # Metadata only: never log message/context, tool arguments, or response text.
            self.last_event = provider_event(
                model,
                'success' if content and content.parts else 'empty_or_rejected',
                (perf_counter() - started) * 1000,
                getattr(response, 'usage_metadata', None),
            )
            if content is None:
                return None, tool_results
            contents.append(content)
            function_calls = [
                part.function_call
                for part in (content.parts or [])
                if part.function_call is not None
            ]
            if not function_calls:
                text = response.text or None
                return text, tool_results

            response_parts = []
            for function_call in function_calls:
                name = function_call.name or ""
                arguments = dict(function_call.args or {})
                result = tool_handler(name, arguments)
                tool_results.append(
                    {
                        "name": name,
                        "arguments": arguments,
                        "result": result,
                    }
                )
                response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=name,
                            id=function_call.id,
                            response=result,
                        )
                    )
                )
            contents.append(
                types.Content(role="user", parts=response_parts)
            )
        return None, tool_results
