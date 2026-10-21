"""Scoped natural revisions and read-only public summaries, no live provider."""

from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import SimpleTestCase, TestCase, override_settings

from menu.models import Category, MenuItem, MenuTag
from ..services.chatbot import ChatbotService
from ..services.conversation_interpreter import ConversationInterpreter
from ..services.conversation_session import ConversationSession
from ..services.conversation_store import ConversationStore
from ..services.recommendation import SearchConstraints
from ..services.tag_extractor import TagExtractor
from .test_budget import NoBudgetProvider


class PreferenceLanguageTests(SimpleTestCase):
    def setUp(self):
        self.interpreter = ConversationInterpreter(TagExtractor())

    def test_drop_spicy_variations_are_not_new_exclusions(self):
        for text in (
            'gak jadi pedas',
            'ga jadi pedas',
            'nggak jadi pedas',
            'enggak jadi pedas',
            'tidak jadi pedas',
            'gajadi pedas',
        ):
            result = self.interpreter._tag_revision(text)
            self.assertEqual(result.operations[0].action, 'DROP')
            self.assertEqual(result.operations[0].tags, ('spicy',))
            self.assertFalse(result.excluded_tags)

    def test_relax_variations_do_not_add_required_chicken(self):
        for text in (
            'sekarang ayam boleh',
            'ayam boleh',
            'ayam sudah boleh lagi',
            'sekarang boleh ayam',
            'boleh ayam',
        ):
            result = self.interpreter._tag_revision(text)
            self.assertEqual(result.operations[0].action, 'RELAX')
            self.assertFalse(result.tags)

    def test_full_summary_queries_only(self):
        for text in (
            'Lagi cariin apa buat aku?',
            'Apa yang sedang kamu carikan?',
            'ringkasan pilihan',
            'lagi cariin apa',
        ):
            self.assertTrue(ChatbotService._is_context_summary(text))

        for text in (
            'apa yang sedang kamu carikan nasi goreng',
            'cari nasi',
            'ringkasan pilihan hapus budget',
        ):
            self.assertFalse(ChatbotService._is_context_summary(text))


class PreferenceLifecycleTests(TestCase):
    def setUp(self):
        food = Category.objects.create(name='Makanan')
        drink = Category.objects.create(name='Minuman')
        tags = {
            name: MenuTag.objects.create(name=name)
            for name in ('spicy', 'chicken', 'rice', 'drink', 'sweet', 'shrimp')
        }
        self.items = {}

        for name, price, category, labels in (
            ('Ayam Geprek', 20000, food, ('spicy', 'chicken', 'rice')),
            ('Nasi Goreng', 18000, food, ('rice',)),
            ('Udang Goreng', 18000, food, ('shrimp',)),
            ('Es Jeruk', 10000, drink, ('drink', 'sweet')),
            ('Es Kelapa', 10000, drink, ('sweet',)),
        ):
            item = MenuItem.objects.create(name=name, price=price, category=category)
            item.tags.add(*(tags[tag] for tag in labels))
            self.items[name] = item

        self.session = SessionStore()
        self.provider = NoBudgetProvider()

    def reply(self, text):
        return ChatbotService(self.session, gemini_client=self.provider).reply(text)

    def graph(self):
        return ConversationSession(self.session).contexts()

    def search(self):
        return ConversationSession(self.session).load_constraints()

    def test_N07_drop_spicy_keeps_price_and_other_requirements(self):
        self.reply('makanan pedas maksimal 25k')
        self.reply('gak jadi pedas')
        self.assertNotIn('spicy', self.search().required_tags)
        self.assertNotIn('spicy', self.search().excluded_tags)
        self.assertEqual(self.search().max_price, 25000)
        self.assertEqual(self.search().category, 'Makanan')

    def test_drop_preserves_soft_target_and_other_tag(self):
        self.reply('makanan ayam pedas sekitar 20k')
        self.reply('gak jadi pedas')
        self.assertIn('chicken', self.search().required_tags)
        self.assertEqual(self.search().soft_target, Decimal(20000))

    def test_N08_natural_switch_keeps_drink_price_local(self):
        self.reply('minuman maksimal 10k')
        result = self.reply('sekarang makanan')
        self.assertEqual(self.search().category, 'Makanan')
        self.assertIsNone(self.search().max_price)
        self.assertTrue(result['recommendations'])

    def test_named_food_switch_needs_no_remove_filter_command(self):
        self.reply('minuman maksimal 10k')
        result = self.reply('ayam geprek')
        self.assertEqual(
            [m.item.pk for m in result['recommendations']], [self.items['Ayam Geprek'].pk]
        )
        self.assertIsNone(self.search().budget)

    def test_N09_relax_chicken_removes_ban_not_adds_requirement(self):
        self.reply('makanan jangan ayam maksimal 25k')
        self.assertIn('chicken', self.search().excluded_tags)
        self.reply('sekarang ayam boleh')
        self.assertNotIn('chicken', self.search().excluded_tags)
        self.assertNotIn('chicken', self.search().required_tags)
        self.assertEqual(self.search().max_price, 25000)

    def test_bare_revision_never_restores_old_food_scope(self):
        self.reply('makanan jangan ayam')
        self.reply('minuman maksimal 10k')
        result = self.reply('sekarang ayam boleh')
        self.assertEqual(self.search().category, 'Minuman')
        self.assertEqual(self.search().max_price, 10000)
        self.assertIn('Tidak ada larangan', result['message'])
        self.reply('balik ke makanan')
        self.assertIn('chicken', self.search().excluded_tags)

    def test_explicit_owned_category_revision_restores_only_that_scope(self):
        self.reply('makanan jangan ayam maksimal 25k')
        self.reply('minuman maksimal 10k')
        self.reply('ayam boleh untuk makanan tadi')
        self.assertEqual(self.search().category, 'Makanan')
        self.assertEqual(self.search().max_price, 25000)
        self.assertNotIn('chicken', self.search().excluded_tags)
        self.reply('balik ke minuman')
        self.assertEqual(self.search().max_price, 10000)

    def test_explicit_current_category_does_not_require_an_archive(self):
        self.reply('makanan jangan ayam maksimal 25k')
        self.reply('ayam boleh untuk makanan tadi')
        self.assertEqual(self.search().category, 'Makanan')
        self.assertNotIn('chicken', self.search().excluded_tags)
        self.assertEqual(self.search().max_price, 25000)

    def test_legacy_unknown_scope_relax_is_not_guessed(self):
        self.reply('makanan jangan ayam')
        self.graph()['active']['legacy_unresolved'] = True
        result = self.reply('ayam boleh')
        self.assertIn('chicken', self.search().excluded_tags)
        self.assertIn('Cakupan larangan lama', result['message'])

    def test_missing_owned_scope_does_not_create_or_steal_one(self):
        self.reply('minuman maksimal 10k')
        before = deepcopy(self.graph()['previous'])
        result = self.reply('ayam boleh untuk makanan tadi')
        self.assertEqual(self.search().category, 'Minuman')
        self.assertEqual(self.graph()['previous'], before)
        self.assertIn('tidak tersedia', result['message'])

    def test_N24_allergy_survives_switch_and_relax(self):
        self.reply('aku alergi udang')
        self.reply('minuman maksimal 10k')
        self.reply('makanan')
        before = deepcopy(self.graph()['safety'])
        result = self.reply('sekarang udang boleh')
        self.assertEqual(self.graph()['safety'], before)
        self.assertIn('keselamatan', result['message'])
        self.assertIn('shrimp', self.search().excluded_tags)

    def test_global_allergy_cannot_be_relaxed_with_all_scope(self):
        self.reply('aku alergi udang')
        self.reply('udang boleh untuk semua pencarian')
        self.assertIn('shrimp', self.graph()['safety']['excluded_tags'])

    def test_new_allergy_declaration_cannot_be_masked_by_relax_suffix(self):
        self.reply('aku alergi udang tapi sekarang udang boleh')
        self.assertIn('shrimp', self.graph()['safety']['excluded_tags'])
        self.assertTrue(self.graph()['safety']['verification_required'])

    def test_bare_spicy_then_drop_needs_no_category_or_chip(self):
        self.reply('mau pedas')
        self.reply('gak jadi pedas')
        self.assertNotIn('spicy', ConversationSession(self.session).load_preferences().tags)
        self.assertNotIn('spicy', self.search().excluded_tags)

    def test_summary_expired_dialog_does_not_reveal_stale_preferences(self):
        self.reply('minuman maksimal 10k')
        before = deepcopy(dict(self.session))

        with patch('recommendation.services.conversation_session.time', return_value=9999999999):
            result = self.reply('ringkasan pilihan')

        self.assertNotIn('10.000', result['message'])
        self.assertEqual(dict(self.session), before)

    def test_global_ordinary_ban_requires_explicit_global_scope(self):
        self.reply('makanan jangan ayam untuk semua pilihan')
        self.assertIn('chicken', self.graph()['safety']['excluded_tags'])
        result = self.reply('ayam boleh')
        self.assertIn('semua pencarian', result['message'])
        self.assertIn('chicken', self.graph()['safety']['excluded_tags'])

    def test_explicit_global_ordinary_relax_does_not_resurrect_on_restore(self):
        self.reply('makanan jangan ayam untuk semua pilihan')
        self.reply('minuman')
        self.reply('ayam boleh untuk semua pencarian')
        self.assertNotIn('chicken', self.graph()['safety']['excluded_tags'])
        self.reply('balik ke makanan')
        self.assertNotIn('chicken', self.search().excluded_tags)

    def test_revision_keeps_overall_and_selected_entries(self):
        self.reply('budget total 30k')
        self.reply('nasi goreng')
        before = deepcopy(self.graph()['plan']['entries'])
        self.reply('gak jadi pedas')
        self.assertEqual(self.graph()['plan']['entries'], before)
        self.assertEqual(self.graph()['overall']['total_budget'], '30000')

    def test_revision_rechecks_exact_current_plan_catalog(self):
        self.reply('budget total 30k')
        self.reply('nasi goreng')
        before = deepcopy(self.graph()['plan'])
        self.items['Nasi Goreng'].is_available = False
        self.items['Nasi Goreng'].save()
        result = self.reply('gak jadi pedas')
        self.assertEqual(self.graph()['plan'], before)
        self.assertIn('belum tersedia', result['message'])

    def test_N28_revision_is_local_without_provider_or_chip(self):
        self.reply('makanan jangan ayam')
        self.reply('sekarang ayam boleh')
        self.assertEqual(self.provider.calls, 0)

    def test_correction_switch_replaces_drink_role(self):
        self.reply('es kelapa')
        self.reply('es jeruk aja')
        self.assertEqual(ConversationSession(self.session).get_focus(), self.items['Es Jeruk'].pk)
        self.assertFalse(self.graph()['plan']['entries'])

    def test_addition_keeps_both_drinks(self):
        self.reply('es kelapa')
        self.reply('sekalian es jeruk')
        self.assertEqual(
            {entry['menu_id'] for entry in self.graph()['plan']['entries']},
            {self.items['Es Kelapa'].pk, self.items['Es Jeruk'].pk},
        )

    def test_alternative_is_search_not_implicit_purchase_or_cancellation(self):
        self.reply('minuman maksimal 10k')
        before = deepcopy(self.graph()['plan'])
        self.reply('yang lain')
        self.assertEqual(self.graph()['plan']['entries'], before['entries'])
        self.assertEqual(self.search().max_price, 10000)

    def test_N29_summary_reads_active_scope_not_archive(self):
        self.reply('makanan pedas maksimal 25k')
        self.reply('minuman maksimal 10k')
        before = deepcopy(dict(self.session))
        result = self.reply('Lagi cariin apa buat aku?')
        self.assertIn('minuman', result['message'])
        self.assertIn('10.000', result['message'])
        self.assertNotIn('25.000', result['message'])
        self.assertNotIn('Pedas', result['message'])
        self.assertEqual(dict(self.session), before)
        self.assertFalse(result['recommendations'])

    def test_summary_no_local_cap_reports_none_even_with_overall_cap(self):
        self.reply('budget total 30k')
        self.reply('minuman')
        result = self.reply('Apa yang sedang kamu carikan?')
        self.assertIn('Tidak ada batas harga per menu', result['message'])
        self.assertIn('Budget total rencana', result['message'])
        self.assertIn('30.000', result['message'])

    def test_summary_approximate_is_not_hard_limit(self):
        self.reply('minuman sekitar 10k')
        result = self.reply('ringkasan pilihan')
        self.assertIn('Perkiraan harga', result['message'])
        self.assertIn('bukan batas tegas', result['message'])

    def test_summary_selected_combo_names_qty_current_minimum(self):
        self.reply('30 ribu buat makan dan minum')
        before = deepcopy(dict(self.session))
        result = self.reply('ringkasan pilihan')
        self.assertIn('Rencana sementara', result['message'])
        self.assertIn('1 ×', result['message'])
        self.assertIn('belum masuk keranjang', result['message'])
        self.assertEqual(dict(self.session), before)

    def test_summary_stale_catalog_does_not_claim_current_total(self):
        self.reply('30 ribu buat makan dan minum')
        self.items['Es Jeruk'].is_available = False
        self.items['Es Jeruk'].save()
        result = self.reply('ringkasan pilihan')
        self.assertIn('belum tersedia', result['message'])
        self.assertIn('belum dapat dipastikan', result['message'])
        self.assertNotIn('Minimum harga saat ini', result['message'])

    def test_summary_no_internal_or_raw_health_metadata(self):
        self.reply('aku alergi udang')
        self.reply('minuman')
        result = self.reply('ringkasan pilihan')

        for forbidden in (
            'verification_required',
            'context_id',
            'schema',
            'SAFETY_RESTRICTION',
            '{',
            'alergi udang',
        ):
            self.assertNotIn(forbidden, result['message'])

        self.assertEqual(self.provider.calls, 0)

    def test_summary_fresh_session_is_read_only(self):
        before = dict(self.session)
        result = self.reply('ringkasan pilihan')
        self.assertIn('Belum ada pencarian', result['message'])
        self.assertEqual(dict(self.session), before)

    def test_summary_keeps_verified_response_plan_contract(self):
        service = ChatbotService(self.session, gemini_client=self.provider)
        service.reply('ringkasan pilihan')
        self.assertEqual(service.response_plan.purpose, 'help')
        self.assertFalse(service.response_plan.selected_menu_ids)

    def test_summary_session_owned(self):
        self.reply('minuman maksimal 10k')
        other = ChatbotService(SessionStore(), gemini_client=self.provider).reply(
            'ringkasan pilihan'
        )
        self.assertNotIn('10.000', other['message'])

    def test_N30_unknown_then_new_menu_keeps_state_consistent(self):
        self.reply('minuman maksimal 10k')
        before = self.search().to_dict()
        self.reply('aku ingin motor')
        self.assertEqual(self.search().to_dict(), before)
        result = self.reply('ayam geprek')
        self.assertEqual(
            [m.item.pk for m in result['recommendations']], [self.items['Ayam Geprek'].pk]
        )
        self.assertIsNone(self.search().max_price)

    def test_canonical_roundtrip_after_revision_preserves_shape6(self):
        self.reply('makanan jangan ayam maksimal 25k')
        self.reply('ayam boleh')
        decoded = ConversationStore._decode(ConversationStore._encode(dict(self.session)))
        self.assertEqual(
            decoded[ConversationSession.CONTEXTS_KEY]['active']['constraints'],
            self.graph()['active']['constraints'],
        )
        self.assertEqual(decoded[ConversationSession.SCHEMA_KEY], 6)

    @override_settings(GEMINI_ENABLED=False)
    def test_http_summary_and_revisions_without_orders_or_api(self):
        from orders.models import Order

        with patch('google.genai.Client', side_effect=AssertionError('No SDK')), patch(
            'recommendation.services.gemini.GeminiClient.generate',
            side_effect=AssertionError('No API'),
        ):
            for text in (
                'makanan jangan ayam maksimal 25k',
                'sekarang ayam boleh',
                'Apa yang sedang kamu carikan?',
            ):
                response = self.client.post(
                    '/api/recommendation/chat/', {'message': text}, content_type='application/json'
                )
                self.assertEqual(response.status_code, 200)

        self.assertIn('25.000', response.json()['message'])
        self.assertEqual(Order.objects.count(), 0)
        self.assertNotIn('cart', self.client.session)
