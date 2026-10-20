"""H1: local resolved intent is observable without expanding provider authority."""
from copy import deepcopy
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import TestCase
from menu.models import Category, MenuItem
from ..services.ai.GeminiInterpreter import validate
from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession
from ..services.conversation_store import ConversationStore
from .test_budget import NoBudgetProvider


class LocalIntentMetadataTests(TestCase):
    def setUp(self):
        food=Category.objects.create(name='Makanan')
        drinks=Category.objects.create(name='Minuman')
        MenuItem.objects.create(name='Nasi Goreng',price=20000,category=food)
        MenuItem.objects.create(name='Es Jeruk',price=10000,category=drinks)
        self.session=SessionStore()
        self.provider=NoBudgetProvider()

    def reply(self,text):
        service=ChatbotService(self.session,gemini_client=self.provider)
        result=service.reply(text)
        return result,service.response_plan

    def graph(self):
        return ConversationSession(self.session).contexts()

    def test_N10_count_correction_has_plan_intent_and_preserves_total(self):
        self.reply('budget 40k untuk 2 orang')
        _,plan=self.reply('jadi 3 orang')
        self.assertEqual(plan.to_dict()['intent'],'UPDATE_PLAN')
        graph=self.graph()
        self.assertEqual(graph['active']['intent'],'UPDATE_PLAN')
        self.assertEqual(graph['transition']['action'],'CORRECT_PREVIOUS')
        self.assertEqual(graph['overall']['person_count'],3)
        self.assertEqual(graph['overall']['total_budget'],'40000')
        self.assertFalse(graph['plan']['entries'])
        self.assertFalse(self.provider.calls)

    def test_N17_soft_budget_intent_does_not_create_a_hard_cap(self):
        _,plan=self.reply('sekitar 20k')
        self.assertEqual(plan.to_dict()['intent'],'UPDATE_BUDGET')
        graph=self.graph()
        self.assertEqual(graph['active']['intent'],'UPDATE_BUDGET')
        self.assertEqual(graph['active']['constraints']['soft_target'],'20000')
        self.assertIsNone(graph['active']['constraints'].get('budget'))
        self.assertFalse(graph['overall'])
        self.assertFalse(self.provider.calls)

    def test_soft_target_replaces_old_cap_without_changing_safety(self):
        self.reply('minuman maksimal 15k')
        before=deepcopy(self.graph()['safety'])
        _,plan=self.reply('sekitar 20k')
        self.assertEqual(plan.to_dict()['intent'],'UPDATE_BUDGET')
        self.assertEqual(self.graph()['active']['constraints']['soft_target'],'20000')
        self.assertIsNone(self.graph()['active']['constraints'].get('budget'))
        self.assertEqual(self.graph()['safety'],before)

    def test_no_owned_plan_or_invalid_count_does_not_report_completed_plan_update(self):
        for text in ('jadi 3 orang','jadi 0 orang','jadi -2 orang'):
            self.session=SessionStore()
            _,plan=self.reply(text)
            self.assertNotEqual(plan.to_dict()['intent'],'UPDATE_PLAN')
            self.assertFalse(self.graph()['overall'])
            self.assertEqual(self.graph()['transition']['action'],'CLARIFY')

    def test_invalid_approximation_keeps_existing_budget(self):
        self.reply('minuman maksimal 15k')
        before=deepcopy(self.graph()['active']['constraints'])
        _,plan=self.reply('sekitar 2000000 rupiah')
        self.assertNotEqual(plan.to_dict()['intent'],'UPDATE_BUDGET')
        self.assertEqual(self.graph()['active']['constraints'],before)

    def test_named_approximate_selection_keeps_selection_intent(self):
        _,plan=self.reply('es jeruk sekitar 20k')
        self.assertEqual(plan.to_dict()['intent'],'SELECT_RECOMMENDATION')
        self.assertEqual(set(plan.allowed_menu_names),{'Es Jeruk'})

    def test_metadata_intents_are_compatible_with_existing_canonical_schema(self):
        for steps in (['budget 40k untuk 2 orang','jadi 3 orang'],['sekitar 20k']):
            self.session=SessionStore()
            for text in steps:self.reply(text)
            graph=self.graph()
            ConversationSession.validate_contexts(graph)
            self.assertTrue(ConversationStore._encode(dict(self.session)))
            self.assertEqual(self.session[ConversationSession.SCHEMA_KEY],6)

    def test_local_numeric_intents_are_not_new_provider_wire_permissions(self):
        wire=dict(intent='RECOMMEND',add_tags=['drink'],remove_tags=[],excluded_tags=[],
                  soft_excluded_tags=[],moods=[],clear_moods=False,max_price=None,
                  prefer_affordable=None,clear_max_price=False,clear_prefer_affordable=False,
                  message_is_meaningful=True)
        self.assertTrue(validate(wire,{'drink'},set()))
        for intent in ('UPDATE_PLAN','UPDATE_BUDGET'):
            self.assertFalse(validate(wire|{'intent':intent},{'drink'},set()))
