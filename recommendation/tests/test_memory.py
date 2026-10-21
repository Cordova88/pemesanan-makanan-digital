"""Phase 6 conversation continuity, references and quota-safe dialog reset."""

import json
from decimal import Decimal

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import SimpleTestCase, TestCase

from menu.models import Category, MenuItem, MenuTag
from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession
from ..services.tag_extractor import Preferences
from ..services.text_generator import TextGenerator


class MemoryGenerator(TextGenerator):
    def __init__(self) -> None:
        self.calls: int = 0

    def generate(self, prompt: str) -> str | None:
        self.calls += 1

        return None


class MemoryStateTests(SimpleTestCase):
    def test_repeated_reset_does_not_replenish_quota_or_clear_cart_auth(self) -> None:
        session = SessionStore()
        state = ConversationSession(session)
        session['cart'] = ['sentinel']
        session['_auth_user_id'] = 'sentinel'
        self.assertTrue(state.consume_gemini_call(1))

        for _ in range(3):
            state.set_entity_ids([1])
            state.remember_rejected([2])
            session[state.INFERRED_KEY] = ['drink']
            state.reset()
            self.assertFalse(state.consume_gemini_call(1))
            self.assertEqual(session['gemini_calls'], 1)
            self.assertEqual(session['cart'], ['sentinel'])
            self.assertEqual(session['_auth_user_id'], 'sentinel')
            self.assertNotIn(state.ENTITY_KEY, session)
            self.assertNotIn(state.REJECTED_KEY, session)
            self.assertNotIn(state.INFERRED_KEY, session)

    def test_menu_id_memory_is_bounded_deduplicated_and_numeric(self) -> None:
        session = SessionStore()
        state = ConversationSession(session)
        state.record_recommendations(list(range(1, 160)), shown_ids=list(range(1, 200)))
        state.remember_rejected(list(range(1, 200)) + [True, -1, 'raw'])
        self.assertEqual(len(state.get_last_recommendation_ids()), 100)
        self.assertEqual(len(state.get_shown_ids()), 100)
        self.assertEqual(len(state.get_explicit_rejections()), 100)
        self.assertTrue(
            all(type(value) is int and value > 0 for value in state.get_explicit_rejections())
        )
        state.allow_requested([199])
        self.assertNotIn(199, state.get_explicit_rejections())

    def test_pending_question_updates_both_authoritative_and_payload_views(self) -> None:
        session = SessionStore()
        state = ConversationSession(session)
        state.save_preferences(Preferences(tags={'rice'}), 'ASKING_FOLLOWUP')
        state.set_last_question('base')
        self.assertEqual(state.load_state()['last_question'], 'base')
        state.set_last_question(None)
        self.assertIsNone(state.get_last_question())
        self.assertIsNone(state.load_state()['last_question'])


class ConversationMemoryTests(TestCase):
    def setUp(self) -> None:
        food = Category.objects.create(name='Makanan')
        drink = Category.objects.create(name='Minuman')
        tags = {
            name: MenuTag.objects.create(name=name)
            for name in ('rice', 'chicken', 'beef', 'spicy', 'drink', 'warm', 'filling')
        }
        self.items = {}

        for name, price, category, names in (
            ('Ayam A', 12000, food, ('rice', 'chicken')),
            ('Ayam B', 14000, food, ('rice', 'chicken', 'spicy')),
            ('Ayam C', 16000, food, ('rice', 'chicken')),
            ('Ayam D', 18000, food, ('rice', 'chicken')),
            ('Ayam E', 22000, food, ('rice', 'chicken')),
            ('Sapi A', 24000, food, ('rice', 'beef')),
            ('Teh Hangat', 8000, drink, ('drink', 'warm')),
        ):
            item = MenuItem.objects.create(name=name, price=Decimal(price), category=category)
            item.tags.add(*(tags[tag] for tag in names))
            self.items[name] = item

        self.session = SessionStore()
        self.generator = MemoryGenerator()

    def reply(self, text: str, action: str | None = None) -> dict:
        return ChatbotService(self.session, gemini_client=self.generator).reply(text, action=action)

    def test_chicken_cheap_no_spicy_more_keeps_combined_constraints(self) -> None:
        self.reply('Aku mau ayam')
        self.reply('Yang murah')
        first = self.reply('Jangan pedas')
        second = self.reply('Ada yang lain?')
        self.assertIn('chicken', second['active_search']['required_tags'])
        self.assertIn('spicy', second['active_search']['excluded_tags'])
        self.assertTrue(second['preferences']['prefer_affordable'])
        ids = {m.item.pk for m in first['recommendations']}
        self.assertTrue(second['recommendations'])
        self.assertFalse(ids & {m.item.pk for m in second['recommendations']})

    def test_food_cheap_chicken_no_spicy_keeps_category(self) -> None:
        self.reply('Aku mau makanan')
        self.reply('yang murah')
        self.reply('yang ayam')
        result = self.reply('tapi jangan pedas')
        self.assertEqual(result['active_search']['category'], 'Makanan')
        self.assertIn('chicken', result['active_search']['required_tags'])
        self.assertTrue(
            all(
                'spicy' not in set(m.item.tags.values_list('name', flat=True))
                for m in result['recommendations']
            )
        )

    def test_additional_base_followup_preserves_protein_and_range(self) -> None:
        self.reply('ayam budget 12-25 ribu')
        result = self.reply('yang nasi')
        self.assertEqual(set(result['active_search']['required_tags']), {'rice', 'chicken'})
        self.assertEqual(result['active_search']['budget']['minimum'], '12000')
        self.assertEqual(result['active_search']['budget']['maximum'], '25000')

    def test_new_protein_followup_replaces_dimension_without_losing_base(self) -> None:
        self.reply('nasi ayam maksimal 25 ribu')
        result = self.reply('yang sapi')
        self.assertEqual(set(result['active_search']['required_tags']), {'rice', 'beef'})
        self.assertEqual([m.item.name for m in result['recommendations']], ['Sapi A'])
        self.assertNotIn('chicken', self.session['recommendation_state']['tags'])

    def test_new_food_and_retry_never_drop_price_bounds(self) -> None:
        self.reply('ayam maksimal 20 ribu')
        result = self.reply('sapi')
        self.assertNotIn('chicken', self.session['recommendation_state']['tags'])
        self.assertFalse(result['recommendations'])
        self.assertEqual(result['active_search']['max_price'], 20000)
        result = self.reply('masa gak ada sapi?')
        self.assertFalse(result['recommendations'])
        self.assertEqual(result['active_search']['budget']['maximum'], '20000')
        result = self.reply('hapus batas budget')
        self.assertEqual([m.item.name for m in result['recommendations']], ['Sapi A'])

    def test_global_positive_correction_keeps_hard_ban_and_budget(self) -> None:
        self.reply('ayam maksimal 25 ribu')
        self.reply('jangan pedas')
        result = self.reply('salah maksudku nasi')
        self.assertIn('spicy', result['active_search']['excluded_tags'])
        self.assertEqual(result['active_search']['max_price'], 25000)
        self.assertTrue(all(m.item.price <= 25000 for m in result['recommendations']))

    def test_exact_identity_survives_budget_followup_until_new_food_request(self) -> None:
        self.reply('ada ayam c?')
        self.assertEqual(self.session[ConversationSession.ENTITY_KEY], [self.items['Ayam C'].pk])
        result = self.reply('maksimal 20 ribu')
        self.assertEqual([m.item.name for m in result['recommendations']], ['Ayam C'])
        result = self.reply('ayam maksimal 25 ribu')
        self.assertNotIn(ConversationSession.ENTITY_KEY, self.session)
        self.assertTrue(result['recommendations'])

    def test_reference_uses_latest_catalog_ids_not_stale_preference_payload(self) -> None:
        self.reply('ayam maksimal 25 ribu')
        latest = self.reply('ada sapi a?')
        self.assertIsNone(self.session.get('last_question'))
        chosen = self.reply('yang pertama')
        self.assertEqual(
            [m.item.pk for m in chosen['recommendations']],
            [m.item.pk for m in latest['recommendations']],
        )
        corrected = self.reply('yang tadi jangan pedas')
        self.assertIn('spicy', corrected['active_search']['excluded_tags'])
        self.assertEqual([m.item.name for m in corrected['recommendations']], ['Sapi A'])

    def test_reference_rechecks_current_price_and_availability(self) -> None:
        self.reply('ada ayam a maksimal 20 ribu?')
        self.items['Ayam A'].price = Decimal(30000)
        self.items['Ayam A'].save(update_fields=['price'])
        self.assertFalse(self.reply('yang pertama')['recommendations'])
        self.items['Ayam A'].price = Decimal(12000)
        self.items['Ayam A'].is_available = False
        self.items['Ayam A'].save(update_fields=['price', 'is_available'])
        self.assertFalse(self.reply('yang pertama')['recommendations'])

    def test_missing_second_reference_clarifies_without_index_error(self) -> None:
        self.reply('ada sapi a?')
        result = self.reply('yang kedua')
        self.assertFalse(result['recommendations'])

    def test_rejected_items_stay_excluded_on_revision_but_explicit_name_overrides(self) -> None:
        first = self.reply('ayam maksimal 25 ribu')
        self.reply('tidak cocok')
        result = self.reply('jangan pedas')
        rejected = {m.item.pk for m in first['recommendations']}
        self.assertFalse(rejected & {m.item.pk for m in result['recommendations']})
        result = self.reply('ada ayam a?')
        self.assertEqual([m.item.name for m in result['recommendations']], ['Ayam A'])

    def test_physical_inference_does_not_remain_as_permanent_drink_preference(self) -> None:
        self.reply('aku haus')
        self.assertIn('drink', self.session[ConversationSession.INFERRED_KEY])
        result = self.reply('sekarang mau nasi')
        self.assertNotIn('drink', self.session['recommendation_state']['tags'])
        self.assertNotIn('drink', result['active_search']['required_tags'])
        self.assertNotIn(ConversationSession.INFERRED_KEY, self.session)
        self.reply('aku haus')
        self.reply('sudah tidak haus')
        self.assertNotIn('drink', self.session['recommendation_state']['excluded_tags'])

    def test_category_switch_archives_previous_local_budget(self) -> None:
        self.reply('minuman maksimal 20 ribu')
        result = self.reply('nasi')
        self.assertTrue(result['recommendations'])
        self.assertIsNone(result['active_search']['max_price'])
        self.assertEqual(
            self.session[ConversationSession.CONTEXTS_KEY]['previous'][-1]['constraints']['budget'][
                'maximum'
            ],
            '20000',
        )
        self.assertNotEqual(result['active_search']['category'], 'Minuman')
        self.assertNotIn('drink', result['active_search']['required_tags'])

    def test_nonfood_turn_does_not_replace_active_food_search(self) -> None:
        first = self.reply('nasi ayam maksimal 25 ribu')
        result = self.reply('ingin motor')
        self.assertFalse(result['recommendations'])
        self.assertEqual(first['active_search'], self.session['recommendation_search'])
        continued = self.reply('yang murah')
        self.assertIn('chicken', continued['active_search']['required_tags'])

    def test_session_roundtrip_is_structured_and_does_not_leak_to_other_session(self) -> None:
        self.reply('nasi ayam maksimal 25 ribu')
        self.reply('cari yang lain')
        self.session = SessionStore()
        self.assertFalse(self.reply('yang pertama')['recommendations'])
        self.reply('ada sapi a?')
        state = json.loads(json.dumps(dict(self.session)))
        self.assertNotIn('ada sapi', json.dumps(state))
        restored = SessionStore()
        restored.update(state)
        result = ChatbotService(restored, gemini_client=self.generator).reply('yang tadi')
        self.assertEqual([m.item.name for m in result['recommendations']], ['Sapi A'])

    def test_reset_clears_dialog_but_keeps_exhausted_provider_counter(self) -> None:
        self.reply('ada ayam a?')
        self.session['gemini_calls'] = 9999
        self.reply('mulai lagi', action='reset')
        self.assertNotIn(ConversationSession.ENTITY_KEY, self.session)
        before = self.generator.calls
        self.reply('ayam')
        self.assertEqual(self.generator.calls, before)
        self.assertEqual(self.session['gemini_calls'], 9999)
