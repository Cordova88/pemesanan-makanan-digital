import json
import logging
from typing import cast
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache

from cart.services import CartService
from menu.models import MenuItem
from menu.selection import MenuSelection

from .services.chatbot import ChatbotService
from .services.conversation_store import ConversationStore, ConversationConflict
from .services.language import tag_label
from .services.recommendation import RecommendationMatch, SearchConstraintsPayload
from .services.tag_extractor import PreferencesPayload
from .services.security import ChatInput, ChatInputError, UsageGuard, request_context
from .services.telemetry import request_event

logger = logging.getLogger(__name__)


def _body(request: HttpRequest) -> dict[str, object]:
    body = json.loads(request.body or "{}")

    if not isinstance(body, dict):
        raise ValueError('Pesan tidak valid.')

    return cast(dict[str, object], body)


def _item(match: RecommendationMatch, explanation: str | None = None) -> dict[str, object]:
    item = match.item
    minimum = MenuSelection.minimum_payable(item)
    result: dict[str, object] = {
        "id": item.id,
        "name": item.name,
        "image_url": item.image.url if item.image else "",
        "category": item.category.name,
        "description": item.description,
        "price": format(item.price, ".2f"),
        "minimum_payable": format(minimum, ".2f") if minimum is not None else None,
        "price_basis": "base_price",
        "final_price_confirmed": False,
        "labels": list(match.labels),
        "match_reasons": list(match.match_reasons),
        "variants": [
            {
                "id": group.id,
                "name": group.name,
                "required": group.is_required,
                "options": [
                    {
                        "id": option.id,
                        "name": option.name,
                        "price_adjustment": format(option.price_adjustment, ".2f"),
                    }
                    for option in group.options.filter(is_active=True)
                ],
            }
            for group in item.variant_groups.filter(is_active=True)
        ],
        "addons": [
            {"id": addon.id, "name": addon.name, "price": format(addon.price, ".2f")}
            for addon in item.allowed_addons.filter(is_active=True, is_available=True)
        ],
    }

    if explanation:
        result["explanation"] = explanation

    return result


def _public_preferences(preferences: PreferencesPayload) -> PreferencesPayload:
    return {
        **preferences,
        "tags": [tag_label(tag) for tag in preferences.get("tags", [])],
        "mood_tags": [tag_label(tag) for tag in preferences.get("mood_tags", [])],
        "excluded_tags": [tag_label(tag) for tag in preferences.get("excluded_tags", [])],
        "soft_excluded_tags": [tag_label(tag) for tag in preferences.get("soft_excluded_tags", [])],
    }


def _public_active_search(search: SearchConstraintsPayload) -> SearchConstraintsPayload:
    return {
        **search,
        "required_tags": [tag_label(tag) for tag in search.get("required_tags", [])],
        "excluded_tags": [tag_label(tag) for tag in search.get("excluded_tags", [])],
    }


@never_cache
@require_POST
def chat(request: HttpRequest) -> JsonResponse:
    request_id = uuid4().hex
    context_token = None
    turn = None

    try:
        body = ChatInput.from_request(request)
        nonce = request.session.get('chatbot_client_id')

        if not isinstance(nonce, str) or len(nonce) != 32:
            # Existing session cookies give parallel first requests one identity.
            nonce = (
                UsageGuard.identity('chat-client:' + request.session.session_key)[:32]
                if request.session.session_key
                else uuid4().hex
            )

        guard = UsageGuard()
        session_id = guard.identity(nonce)
        client_id = guard.identity(str(request.META.get('REMOTE_ADDR', 'unknown'))[:128])
        context_token = request_context.set(
            {'request_id': request_id, 'session': session_id, 'client': client_id}
        )

        if not guard.allow_request(session_id, client_id):
            response = JsonResponse(
                {
                    'error': (
                        'Layanan sementara belum tersedia.'
                        if guard.unavailable
                        else 'Terlalu banyak pesan. Coba lagi sebentar.'
                    )
                },
                status=503 if guard.unavailable else 429,
            )
            response['Retry-After'] = '60'
            response['X-Request-ID'] = request_id

            request_event(
                request_id,
                'guard_unavailable' if guard.unavailable else 'rate_limited',
                response.status_code,
            )

            return response

        request.session['chatbot_client_id'] = nonce
        turn = ConversationStore(nonce, request.session, body.revision)
        service_result = ChatbotService(turn.session).reply(
            body.message,
            body.action == 'more',
            body.action,
        )
        explanations = service_result.pop("explanations", {})
        result: dict[str, object] = dict(service_result)
        result["recommendations"] = [
            _item(item, explanations.get(item.item.id))
            for item in service_result["recommendations"]
        ]
        result["preferences"] = _public_preferences(service_result["preferences"])

        if "active_search" in service_result:
            result["active_search"] = _public_active_search(service_result["active_search"])

        revision = turn.commit()

        turn.mirror(request.session, enabled=settings.DEBUG)

        result['revision'] = revision
        response = JsonResponse(result)
        response['X-Request-ID'] = request_id

        request_event(request_id, 'success', 200)

        return response

    except ConversationConflict as error:
        # Do not let SessionMiddleware save a stale main-session mirror.
        request.session.modified = False
        response = JsonResponse(
            {
                'error': 'Percakapan sudah berubah. Kirim ulang pesan berdasarkan pilihan terbaru.',
                'revision': error.revision,
            },
            status=409,
        )
        response['X-Request-ID'] = request_id

        request_event(request_id, 'revision_conflict', 409)

        return response

    except ChatInputError as error:

        response = JsonResponse({'error': str(error)}, status=error.status)
        response['X-Request-ID'] = request_id

        request_event(request_id, 'input_rejected', error.status)

        return response

    except Exception:
        if turn is not None:
            try:
                turn.preserve_usage()
            except Exception:
                pass  # Shared provider quotas remain authoritative on storage failure.

        request.session.modified = False

        logger.warning('Chatbot request failed (request_id=%s)', request_id)

        response = JsonResponse({'error': 'Layanan sementara belum tersedia.'}, status=503)
        response['X-Request-ID'] = request_id

        request_event(request_id, 'internal_error', 503)

        return response

    finally:
        if context_token is not None:
            request_context.reset(context_token)


@require_POST
def add_to_cart(request: HttpRequest) -> JsonResponse:
    try:
        body = _body(request)
        item = MenuItem.objects.get(pk=body.get("menu_item_id"))

        CartService(request.session).add_item(
            item.id,
            int(cast(str | int, body.get("quantity", 1))),
            body.get("variant_ids", []),
            body.get("addon_ids", []),
        )

        return JsonResponse({"message": "✅ Sudah masuk ke keranjang!"})

    except (
        MenuItem.DoesNotExist,
        ValidationError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@require_GET
def chatbot_page(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "recommendation/chatbot.html",
        {'gemini_enabled': bool(getattr(settings, 'GEMINI_ENABLED', False))},
    )
