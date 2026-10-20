"""V3.2 Phase 1 catalog identities/categories, without live provider or customer data."""
from copy import deepcopy
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, override_settings

from menu.models import Category, MenuItem, MenuItemAlias, MenuTag, VariantGroup, VariantOption
from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession
from ..services.entity_resolver import EntityResolver
from .test_entities import FakeGenerator


class PartialIdentityTests(SimpleTestCase):
    def setUp(self) -> None:
        self.resolver = EntityResolver(
            ((1, 'Es Kelapa'), (2, 'Es Jeruk'), (3, 'Jus Jeruk'), (4, 'Ayam Geprek')),
            ('ayam', 'es', 'minuman', 'pedas'), aliases=((1, 'kelapa muda segar'),),
        )

    def test_unique_partial_and_full_names_are_catalog_grounded(self) -> None:
        for text in ('mau kelapa', 'yang kelapa', 'aku mau es kelapa', 'kelapa aja'):
            with self.subTest(text=text):
                self.assertEqual(self.resolver.resolve(text).menu_ids, (1,))

    def test_ambiguous_partial_keeps_candidate_ids(self) -> None:
        result = self.resolver.resolve('jeruk')
        self.assertEqual(result.domain_status, 'AMBIGUOUS_CATALOG')
        self.assertEqual(set(result.menu_ids), {2, 3})

    def test_alias_is_exact_and_does_not_invent_a_new_identity(self) -> None:
        self.assertEqual(self.resolver.resolve('mau kelapa muda segar').menu_ids, (1,))

    def test_generic_terms_and_unknown_compounds_do_not_select_partial(self) -> None:
        self.assertIsNone(self.resolver.resolve('mau ayam'))
        self.assertIsNone(self.resolver.resolve('yang tadi'))
        self.assertEqual(self.resolver.resolve('mau kelapa quantum').domain_status, 'AMBIGUOUS_REQUEST')

    def test_past_consumption_negation_and_correction_keep_clause_roles(self) -> None:
        self.assertIsNone(self.resolver.resolve('aku sudah makan kelapa'))
        result = self.resolver.resolve('bukan kelapa, es jeruk aja')
        self.assertEqual(result.menu_ids, (2,))
        self.assertEqual(result.rejected_menu_ids, (1,))
        self.assertEqual(self.resolver.resolve('jangan kelapa').rejected_menu_ids, (1,))

    def test_new_catalog_names_work_without_a_named_food_dictionary(self) -> None:
        resolver = EntityResolver(((8, 'Teh Arunika'), (9, 'Roti Senja')))
        self.assertEqual(resolver.resolve('mau arunika').menu_ids, (8,))

    def test_same_alias_on_two_items_requires_clarification(self) -> None:
        resolver = EntityResolver(((1, 'Es Kelapa'), (2, 'Es Jeruk')),
                                  aliases=((1, 'pilihan taman'), (2, 'pilihan taman')))
        self.assertEqual(resolver.resolve('mau pilihan taman').domain_status, 'AMBIGUOUS_CATALOG')

    def test_exact_canonical_name_precedes_conflicting_alias(self) -> None:
        resolver = EntityResolver(((1, 'Es Kelapa'), (2, 'Es Jeruk')), aliases=((2, 'es kelapa'),))
        self.assertEqual(resolver.resolve('mau es kelapa').menu_ids, (1,))

    def test_object_followup_uses_current_object(self) -> None:
        self.assertEqual(self.resolver.resolve('kalau guling?').requested_entity, 'guling')
        self.assertEqual(self.resolver.resolve('kalau glorp?').domain_status, 'AMBIGUOUS_REQUEST')

    def test_catalog_existence_questions_resolve_unique_identity(self) -> None:
        for text in ('Kelapa ada?', 'Ada kelapa?', 'Es kelapa tersedia?',
                     'Jual es kelapa?', 'Punya kelapa?', 'Apakah kelapa tersedia?'):
            with self.subTest(text=text):
                result = self.resolver.resolve(text)
                self.assertIsNotNone(result)
                self.assertEqual(result.domain_status, 'IN_CATALOG')
                self.assertEqual(result.menu_ids, (1,))

    def test_postposed_question_preserves_ambiguous_candidates(self) -> None:
        result = self.resolver.resolve('Jeruk ada?')
        self.assertIsNotNone(result)
        self.assertEqual(result.domain_status, 'AMBIGUOUS_CATALOG')
        self.assertEqual(set(result.menu_ids), {2, 3})

    def test_existence_questions_use_dynamic_names_and_aliases(self) -> None:
        resolver = EntityResolver(((8, 'Teh Arunika'), (9, 'Roti Senja')),
                                  aliases=((8, 'embun pagi'),))
        for text in ('Arunika tersedia?', 'Embun pagi ada?', 'Punya arunika?'):
            with self.subTest(text=text):
                result = resolver.resolve(text)
                self.assertIsNotNone(result)
                self.assertEqual(result.menu_ids, (8,))
        conflicting = EntityResolver(((1, 'Es Kelapa'), (2, 'Es Jeruk')),
                                     aliases=((2, 'es kelapa'),))
        self.assertEqual(conflicting.resolve('Es kelapa tersedia?').menu_ids, (1,))

    def test_existence_question_does_not_accept_unknown_compounds_or_negation(self) -> None:
        for text in ('kelapa quantum ada?', 'kelapa quantum tersedia?',
                     'kelapa tidak tersedia?', 'aku sudah minum kelapa',
                     'aku sudah minum kelapa tersedia?', 'kelapanya ada?'):
            with self.subTest(text=text):
                result = self.resolver.resolve(text)
                self.assertTrue(result is None or result.domain_status != 'IN_CATALOG')
        self.assertEqual(self.resolver.resolve('jangan kelapa').rejected_menu_ids, (1,))

    def test_partial_question_control_paraphrases_still_resolve(self) -> None:
        for text in ('Mau kelapa.', 'Yang kelapa.', 'Pengen kelapa.',
                     'Kelapa aja deh.', 'kelapa muda segar'):
            with self.subTest(text=text):
                self.assertEqual(self.resolver.resolve(text).menu_ids, (1,))


class CatalogLanguageIntegrationTests(TestCase):
    def setUp(self) -> None:
        self.food = Category.objects.create(name='Makanan')
        self.drinks = Category.objects.create(name='Minuman')
        self.snacks = Category.objects.create(name='Camilan')
        self.desserts = Category.objects.create(name='Dessert')
        self.kelapa = MenuItem.objects.create(name='Es Kelapa', category=self.drinks, price=10000)
        self.jeruk = MenuItem.objects.create(name='Es Jeruk', category=self.drinks, price=10000)
        self.jus = MenuItem.objects.create(name='Jus Jeruk', category=self.drinks, price=12000)
        self.ayam = MenuItem.objects.create(name='Ayam Geprek', category=self.food, price=18000)
        self.kentang = MenuItem.objects.create(name='Kentang Panggang', category=self.snacks, price=8000)
        self.puding = MenuItem.objects.create(name='Puding Mangga', category=self.desserts, price=7000)
        snack = MenuTag.objects.create(name='snack')
        self.kentang.tags.add(snack)
        self.session = SessionStore()
        self.generator = FakeGenerator()

    def reply(self, text: str) -> dict:
        return ChatbotService(self.session, gemini_client=self.generator).reply(text)

    @staticmethod
    def ids(response: dict) -> set[int]:
        return {match.item.pk for match in response['recommendations']}

    def test_partial_selects_kelapa_not_cold_drink_tag(self) -> None:
        self.assertEqual(self.ids(self.reply('yang kelapa')), {self.kelapa.pk})
        self.assertEqual(self.generator.prompts, [])

    def test_existence_questions_return_current_catalog_price_without_provider(self) -> None:
        for text in ('Kelapa ada?', 'Ada kelapa?', 'Es kelapa tersedia?',
                     'Jual es kelapa?', 'Punya kelapa?'):
            with self.subTest(text=text):
                self.session = SessionStore()
                response = self.reply(text)
                self.assertEqual(self.ids(response), {self.kelapa.pk})
                self.assertEqual(response['recommendations'][0].item.price, self.kelapa.price)
                self.assertNotIn('cart', self.session)
        self.assertEqual(self.generator.prompts, [])

    def test_ambiguous_existence_question_preserves_business_search(self) -> None:
        self.reply('mau ayam geprek')
        old_search = dict(self.session['recommendation_search'])
        old_focus = ConversationSession(self.session).get_focus()
        response = self.reply('Jeruk ada?')
        self.assertFalse(response['recommendations'])
        self.assertIn('Es Jeruk', response['message'])
        self.assertIn('Jus Jeruk', response['message'])
        self.assertEqual(self.session['recommendation_search'], old_search)
        self.assertEqual(ConversationSession(self.session).get_focus(), old_focus)
        self.assertEqual(self.generator.prompts, [])

    def test_existence_questions_do_not_override_availability_or_local_budget(self) -> None:
        for obj, field in ((self.kelapa, 'is_active'), (self.kelapa, 'is_available'),
                           (self.drinks, 'is_active')):
            with self.subTest(field=field, kind=type(obj).__name__):
                setattr(obj, field, False)
                obj.save(update_fields=[field])
                self.session = SessionStore()
                self.assertFalse(self.reply('Kelapa ada?')['recommendations'])
                setattr(obj, field, True)
                obj.save(update_fields=[field])
        self.session = SessionStore()
        self.reply('minuman maksimal 5000')
        self.assertFalse(self.reply('Kelapa ada?')['recommendations'])
        self.assertEqual(self.session['recommendation_search']['budget']['maximum'], '5000')
        self.assertEqual(self.kelapa.price, 10000)
        self.assertEqual(self.generator.prompts, [])

    def test_ambiguity_names_candidates_without_selecting_or_changing_search(self) -> None:
        self.reply('mau ayam geprek')
        old = dict(self.session['recommendation_search'])
        response = self.reply('jeruk')
        self.assertFalse(response['recommendations'])
        self.assertIn('Es Jeruk', response['message'])
        self.assertIn('Jus Jeruk', response['message'])
        self.assertEqual(self.session['recommendation_search'], old)
        self.assertEqual(self.ids(self.reply('es jeruk')), {self.jeruk.pk})
        self.assertEqual(self.generator.prompts, [])

    def test_active_normalized_database_alias_works(self) -> None:
        alias = MenuItemAlias.objects.create(menu_item=self.kelapa, phrase='  PILIHAN   TAMAN ')
        self.assertEqual(alias.phrase, 'pilihan taman')
        self.assertEqual(self.ids(self.reply('aku mau pilihan taman')), {self.kelapa.pk})

    def test_alias_collision_is_clarified(self) -> None:
        for item in (self.kelapa, self.jeruk):
            MenuItemAlias.objects.create(menu_item=item, phrase='pilihan taman')
        response = self.reply('mau pilihan taman')
        self.assertFalse(response['recommendations'])
        self.assertIn('Es Kelapa', response['message'])
        self.assertIn('Es Jeruk', response['message'])

    def test_inactive_alias_item_and_category_cannot_produce_cards(self) -> None:
        alias = MenuItemAlias.objects.create(menu_item=self.kelapa, phrase='pilihan taman')
        for obj, field in ((alias, 'is_active'), (self.kelapa, 'is_active'),
                           (self.drinks, 'is_active'), (self.kelapa, 'is_available')):
            with self.subTest(field=field, kind=type(obj).__name__):
                setattr(obj, field, False)
                obj.save(update_fields=[field])
                self.session = SessionStore()
                self.assertFalse(self.reply('mau pilihan taman')['recommendations'])
                setattr(obj, field, True)
                obj.save(update_fields=[field])

    def test_general_requests_use_current_catalog_categories(self) -> None:
        for text, expected in (('aku mau makan', {self.ayam.pk}),
                               ('aku mau minum', {self.kelapa.pk, self.jeruk.pk, self.jus.pk}),
                               ('mau ngemil', {self.kentang.pk}), ('mau dessert', {self.puding.pk})):
            with self.subTest(text=text):
                self.session = SessionStore()
                self.assertEqual(self.ids(self.reply(text)), expected)
        self.assertEqual(self.generator.prompts, [])

    def test_new_category_and_alias_do_not_require_code_changes(self) -> None:
        category = Category.objects.create(name='Hidangan Kebun')
        item = MenuItem.objects.create(name='Pilihan Arunika', category=category, price=6000)
        self.assertEqual(self.ids(self.reply('mau hidangan kebun')), {item.pk})

    def test_category_name_collision_remains_category_workflow(self) -> None:
        other = MenuItem.objects.create(name='Minuman', category=self.food, price=2000)
        self.assertNotIn(other.pk, self.ids(self.reply('mau minuman')))

    def test_incidental_past_consumption_does_not_select_food(self) -> None:
        self.assertFalse(self.reply('aku sudah makan')['recommendations'])
        self.assertFalse(self.reply('aku sudah makan kelapa')['recommendations'])
        self.assertFalse(self.reply('aku sudah minum es jeruk')['recommendations'])

    def test_negation_and_price_filter_remain_authoritative_for_partial_item(self) -> None:
        self.assertFalse(self.reply('mau kelapa maksimal 5000')['recommendations'])
        self.session = SessionStore()
        self.reply('jangan kelapa')
        self.assertIn(self.kelapa.pk, ConversationSession(self.session).get_explicit_rejections())

    def test_object_followups_and_unknown_objects_do_not_mutate_search(self) -> None:
        self.reply('mau ayam geprek')
        old = dict(self.session['recommendation_search'])
        for text, obj in (('ada bantal?', 'bantal'), ('kalau guling?', 'guling'), ('mau glorp', 'glorp')):
            response = self.reply(text)
            self.assertIn(obj, response['message'].casefold())
            self.assertFalse(response['recommendations'])
            self.assertEqual(self.session['recommendation_search'], old)

    def test_named_reference_restores_only_owned_item_scope(self) -> None:
        self.reply('minuman 10k')
        self.reply('es kelapa')
        self.reply('makanan maksimal 20000')
        self.assertEqual(self.ids(self.reply('balik ke kelapa')), {self.kelapa.pk})
        self.assertEqual(self.session['recommendation_search'].get('max_price'), 10000)
        self.session = SessionStore()
        self.assertFalse(self.reply('balik ke kelapa')['recommendations'])

    def _archive_candidate_only_kelapa(self, budget: str = '10k') -> None:
        for index in range(1, 4):
            MenuItem.objects.get_or_create(name=f'Air Kebun {index}', category=self.drinks,
                                           defaults={'price': index * 1000})
        self.reply('minuman ' + budget)
        state = ConversationSession(self.session)
        self.assertIn(self.kelapa.pk, state.get_candidates())
        self.assertNotIn(self.kelapa.pk, state.get_last_recommendation_ids())
        self.reply('ayam geprek')

    def test_named_restore_accepts_unshown_candidate_from_owned_search(self) -> None:
        self._archive_candidate_only_kelapa()
        result = self.reply('balik ke kelapa deh')
        self.assertEqual(self.ids(result), {self.kelapa.pk})
        self.assertEqual(self.session['recommendation_search']['budget']['maximum'], '10000')
        self.assertEqual(ConversationSession(self.session).get_focus(), self.kelapa.pk)
        self.assertEqual(self.session[ConversationSession.CONTEXTS_KEY]['transition']['action'],
                         'REFER_TO_PREVIOUS')
        self.assertNotIn('cart', self.session)
        self.assertEqual(self.generator.prompts, [])

    def test_named_reference_returns_to_prior_choice_in_current_search(self) -> None:
        # Exact original historical T03, with no category switch to create an archive.
        self.reply('mau es kelapa')
        self.reply('eh es jeruk aja')
        result = self.reply('balik ke kelapa deh')
        self.assertEqual(self.ids(result), {self.kelapa.pk})
        self.assertEqual(ConversationSession(self.session).get_focus(), self.kelapa.pk)
        self.assertEqual(self.generator.prompts, [])

    def test_bare_candidate_name_does_not_reactivate_archived_budget(self) -> None:
        self._archive_candidate_only_kelapa()
        result = self.reply('es kelapa')
        self.assertEqual(self.ids(result), {self.kelapa.pk})
        self.assertIsNone(self.session['recommendation_search'].get('budget'))
        self.assertIsNone(self.session['recommendation_search'].get('max_price'))

    @override_settings(CHATBOT_DIALOG_IDLE_SECONDS=60)
    def test_named_candidate_restore_rejects_expired_frame(self) -> None:
        self._archive_candidate_only_kelapa()
        graph = self.session[ConversationSession.CONTEXTS_KEY]
        graph['previous'][-1]['updated_at'] -= 61
        old_search = deepcopy(self.session['recommendation_search'])
        self.assertFalse(self.reply('balik ke kelapa deh')['recommendations'])
        self.assertEqual(self.session['recommendation_search'], old_search)
        self.assertEqual(ConversationSession(self.session).get_focus(), self.ayam.pk)

    def test_named_candidate_restore_revalidates_current_price(self) -> None:
        self._archive_candidate_only_kelapa()
        self.kelapa.price = 15000
        self.kelapa.save(update_fields=['price'])
        self.assertFalse(self.reply('balik ke kelapa deh')['recommendations'])
        self.assertEqual(self.session[ConversationSession.CONTEXTS_KEY]['plan']['entries'], [])
        self.assertEqual(self.generator.prompts, [])

    def test_named_candidate_restore_revalidates_required_options(self) -> None:
        self._archive_candidate_only_kelapa()
        group = VariantGroup.objects.create(menu_item=self.kelapa, name='Ukuran', is_required=True)
        VariantOption.objects.create(group=group, name='Besar', price_adjustment=5000)
        self.assertFalse(self.reply('balik ke kelapa deh')['recommendations'])
        self.assertEqual(self.session[ConversationSession.CONTEXTS_KEY]['plan']['entries'], [])

    def test_unavailable_named_reference_does_not_restore_different_drink(self) -> None:
        for obj, field in ((self.kelapa, 'is_available'), (self.kelapa, 'is_active'),
                           (self.drinks, 'is_active')):
            with self.subTest(field=field, kind=type(obj).__name__):
                self.session = SessionStore()
                self._archive_candidate_only_kelapa()
                old_search = deepcopy(self.session['recommendation_search'])
                old_plan = deepcopy(self.session[ConversationSession.CONTEXTS_KEY]['plan'])
                setattr(obj, field, False)
                obj.save(update_fields=[field])
                try:
                    self.assertFalse(self.reply('balik ke kelapa deh')['recommendations'])
                    self.assertEqual(self.session['recommendation_search'], old_search)
                    self.assertEqual(self.session[ConversationSession.CONTEXTS_KEY]['plan'], old_plan)
                    self.assertEqual(ConversationSession(self.session).get_focus(), self.ayam.pk)
                finally:
                    setattr(obj, field, True)
                    obj.save(update_fields=[field])

    def test_named_restore_cannot_claim_item_outside_archived_candidates(self) -> None:
        self.reply('minuman maksimal 5000')
        self.assertNotIn(self.kelapa.pk, ConversationSession(self.session).get_candidates())
        self.reply('ayam geprek')
        old_search = deepcopy(self.session['recommendation_search'])
        self.assertFalse(self.reply('balik ke kelapa deh')['recommendations'])
        self.assertEqual(self.session['recommendation_search'], old_search)

    def test_ambiguous_named_restore_keeps_search_and_plan(self) -> None:
        self._archive_candidate_only_kelapa('15k')
        old_search = deepcopy(self.session['recommendation_search'])
        old_plan = deepcopy(self.session[ConversationSession.CONTEXTS_KEY]['plan'])
        result = self.reply('balik ke jeruk deh')
        self.assertFalse(result['recommendations'])
        self.assertIn('Es Jeruk', result['message'])
        self.assertIn('Jus Jeruk', result['message'])
        self.assertEqual(self.session['recommendation_search'], old_search)
        self.assertEqual(self.session[ConversationSession.CONTEXTS_KEY]['plan'], old_plan)

    def test_explicit_item_reference_revalidates_its_own_cap_after_price_change(self) -> None:
        self.reply('minuman 10k')
        self.reply('es kelapa')
        self.reply('makanan maksimal 20000')
        self.kelapa.price = 15000
        self.kelapa.save(update_fields=['price'])
        self.assertFalse(self.reply('balik ke kelapa')['recommendations'])

    def test_bare_partial_does_not_restore_archived_category_budget(self) -> None:
        self.reply('minuman maksimal 5000')
        self.reply('mau ayam geprek')
        self.assertEqual(self.ids(self.reply('mau kelapa')), {self.kelapa.pk})
        self.assertIsNone(self.session['recommendation_search'].get('max_price'))

    def test_category_negation_does_not_request_that_category(self) -> None:
        self.assertFalse(self.reply('aku tidak mau makan')['recommendations'])

    def test_alias_matching_does_not_swallow_existing_tag_alias(self) -> None:
        from menu.models import MenuTagAlias
        smoky = MenuTag.objects.create(name='smoky')
        MenuTagAlias.objects.create(tag=smoky, phrase='panggang asap')
        item = MenuItem.objects.create(name='Sate Asap', category=self.food, price=9000)
        item.tags.add(smoky)
        self.assertEqual(self.ids(self.reply('mau yang panggang asap')), {item.pk})
        self.assertEqual(self.session['recommendation_state']['tags'], ['smoky'])

    def test_alias_is_not_authority_for_late_availability(self) -> None:
        MenuItemAlias.objects.create(menu_item=self.kelapa, phrase='pilihan taman')
        service = ChatbotService(self.session, gemini_client=self.generator)
        self.kelapa.is_available = False
        self.kelapa.save(update_fields=['is_available'])
        self.assertFalse(service.reply('mau pilihan taman')['recommendations'])

    def test_alias_validation_unique_per_item_and_staff_admin(self) -> None:
        for phrase in ('   ', 'x' * 101):
            with self.assertRaises(ValidationError):
                MenuItemAlias.objects.create(menu_item=self.kelapa, phrase=phrase)
        MenuItemAlias.objects.create(menu_item=self.kelapa, phrase='Pilihan Taman')
        with self.assertRaises(IntegrityError), transaction.atomic():
            MenuItemAlias.objects.create(menu_item=self.kelapa, phrase='  pilihan taman ')
        from django.contrib import admin
        self.assertIn(MenuItemAlias, admin.site._registry)

    def test_http_contract_and_no_transaction_side_effects(self) -> None:
        with patch('recommendation.services.gemini.GeminiClient.generate', return_value=None):
            response = self.client.post('/api/recommendation/chat/', {'message': 'yang kelapa'}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([card['id'] for card in response.json()['recommendations']], [self.kelapa.pk])
        from orders.models import Order
        self.assertEqual(Order.objects.count(), 0)
