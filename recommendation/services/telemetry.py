"""Operational metadata only. Cost is unknown unless a verified tariff exists."""

import json
import logging
from datetime import datetime, timezone
from typing import TypedDict

from .security import correlation_id

logger = logging.getLogger('recommendation.services.gemini')


class ProviderEvent(TypedDict):
    timestamp: str
    request_id: str
    event: str
    model: str
    outcome: str
    latency_ms: float
    input_tokens: int | None
    output_tokens: int | None
    thinking_tokens: int | None
    cached_tokens: int | None
    total_tokens: int | None
    estimated_cost: None
    provider_called: bool


def token_count(metadata: object, name: str) -> int | None:
    value = getattr(metadata, name, None)

    return value if type(value) is int and value >= 0 else None


def request_event(request_id: str, outcome: str, status: int) -> None:
    logger.info(
        json.dumps(
            {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'request_id': request_id,
                'event': 'chat_request',
                'outcome': outcome,
                'status': status,
            }
        )
    )


def provider_event(
    model: str, outcome: str, latency_ms: float, metadata: object = None, *, failed: bool = False
) -> ProviderEvent:
    event: ProviderEvent = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'request_id': correlation_id(),
        'event': 'provider_attempt',
        'model': model[:80],
        'outcome': outcome,
        'latency_ms': round(max(0, latency_ms), 3),
        'input_tokens': token_count(metadata, 'prompt_token_count'),
        'output_tokens': token_count(metadata, 'candidates_token_count'),
        'thinking_tokens': token_count(metadata, 'thoughts_token_count'),
        'cached_tokens': token_count(metadata, 'cached_content_token_count'),
        'total_tokens': token_count(metadata, 'total_token_count'),
        'estimated_cost': None,
        'provider_called': outcome
        in {'success', 'empty_or_rejected', 'TimeoutError', 'provider_error'},
    }
    logger.log(logging.WARNING if failed else logging.INFO, json.dumps(event))

    return event


def provider_failure_event(category: str, http_status: int | None = None) -> None:
    """Failure metadata only: do not stringify exceptions or response bodies."""

    if category not in {
        'timeout',
        'transport',
        'authentication',
        'rate_limited',
        'invalid_request',
        'upstream',
        'api_error',
        'unexpected',
    }:
        raise ValueError('Unsupported provider failure category')

    if http_status is not None and (type(http_status) is not int or not 100 <= http_status <= 599):
        raise ValueError('Invalid provider HTTP status')

    logger.warning(
        json.dumps(
            {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'request_id': correlation_id(),
                'event': 'provider_failure',
                'category': category,
                'http_status': http_status,
                'usage_available': False,
            }
        )
    )
