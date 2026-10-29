"""Check lazy Python 3.14 annotations and the internal/wire response boundary."""

import importlib
import inspect
from decimal import Decimal
from typing import get_type_hints
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from menu.models import Category, MenuItem, MenuTag
from ..services.recommendation import RecommendationMatch
from ..services.response_types import ChatbotResponse, QuickReply
from ..services.tag_extractor import Preferences


class AnnotationResolutionTests(SimpleTestCase):
    def test_all_service_and_view_callable_annotations_resolve(self) -> None:
        names = (
            'ai.assistant',
            'chatbot',
            'conversation_session',
            'conversation_store',
            'gemini',
            'language',
            'recommendation',
            'response_types',
            'security',
            'tag_extractor',
            'telemetry',
            'text_generator',
        )
        modules = [importlib.import_module(f'recommendation.services.{name}') for name in names]
        modules.append(importlib.import_module('recommendation.views'))
        checked = 0

        for module in modules:
            namespace = dict(vars(module))
            functions = []

            for value in vars(module).values():
                if getattr(value, '__module__', None) != module.__name__:
                    continue

                if inspect.isfunction(value):
                    functions.append(value)
                elif inspect.isclass(value):
                    get_type_hints(value, globalns=namespace)

                    for member in vars(value).values():
                        if isinstance(member, (staticmethod, classmethod)):
                            functions.append(member.__func__)
                        elif isinstance(member, property) and member.fget is not None:
                            functions.append(member.fget)
                        elif inspect.isfunction(member):
                            functions.append(member)

            for function in functions:
                function = inspect.unwrap(function)

                # Python 3.14 generates this hook; it is not a source callable.
                if function.__name__ == '__annotate__':
                    continue

                with self.subTest(function=f'{module.__name__}.{function.__qualname__}'):
                    signature = inspect.signature(function)
                    hints = get_type_hints(function, globalns=namespace)
                    self.assertIn('return', hints)

                    for name in signature.parameters:
                        if name not in ('self', 'cls'):
                            self.assertIn(name, hints)

                checked += 1

        self.assertGreater(checked, 60)

    def test_response_schemas_preserve_required_and_optional_keys(self) -> None:
        self.assertEqual(
            ChatbotResponse.__required_keys__,
            {
                'message',
                'state',
                'preferences',
                'recommendations',
                'quick_replies',
            },
        )
        self.assertEqual(ChatbotResponse.__optional_keys__, {'active_search'})
        self.assertEqual(QuickReply.__required_keys__, {'label', 'value'})
        self.assertEqual(QuickReply.__optional_keys__, {'action'})


class TypedResponseBoundaryTests(TestCase):
    def test_wire_response_serializes_recommendations_without_internal_fields(self) -> None:
        category = Category.objects.create(name='Makanan')
        item = MenuItem.objects.create(
            name='Nasi', category=category, price=Decimal('10000.50')
        )
        result = {
            'message': 'Ini pilihan untukmu.',
            'state': 'RECOMMENDING',
            'preferences': Preferences().to_dict(state='RECOMMENDING'),
            'recommendations': [RecommendationMatch(item, 4, ('Nasi',), ('Nasi',))],
            'quick_replies': [],
        }

        with patch('recommendation.views.ChatbotService') as service:
            service.return_value.reply.return_value = result
            response = self.client.post(
                '/api/recommendation/chat/',
                {'message': 'mau nasi'},
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn('explanations', payload)
        self.assertEqual(payload['recommendations'][0]['price'], '10000.50')
        self.assertEqual(payload['recommendations'][0]['id'], item.pk)
        self.assertNotIn('explanation', payload['recommendations'][0])
