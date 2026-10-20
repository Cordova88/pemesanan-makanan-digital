"""Phase 2 soft/hard budgets and role-first money; synthetic data, no live AI."""
from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import SimpleTestCase, TestCase

from menu.models import Category, MenuItem, MenuTag
from ..services.budget import BudgetConstraint
from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession
from ..services.conversation_store import ConversationStore, ConversationStoreUnavailable
from ..services.language import IndonesianPriceParser
from ..services.recommendation import RecommendationService, SearchConstraints
from ..services.tag_extractor import Preferences
from .test_budget import NoBudgetProvider


class RoleFirstParserTests(SimpleTestCase):
    def setUp(self) -> None:
        self.parser = IndonesianPriceParser()

    def test_equivalent_money_formats_and_word_amounts(self) -> None:
        examples = {'10k':10000, '10rb':10000, '10 ribu':10000, 'Rp10.000':10000,
                    '10000':10000, 'sepuluh ribu':10000, 'dua puluh lima ribu':25000,
                    'seratus dua puluh lima ribu':125000, 'tiga belas ribu':13000,
                    '30,5k':30500, 'Rp10.000,50':Decimal('10000.50'), '10 rupiah':10}
        for text, value in examples.items():
            with self.subTest(text=text):
                result = self.parser.parse('maksimal ' + text)
                self.assertEqual(result.constraint.maximum, Decimal(value))
                self.assertEqual([m.role for m in result.numeric_roles], ['MONEY'])

    def test_approximate_prices_never_become_hard_bounds(self) -> None:
        for text in ('sekitar 20k', 'kisaran dua puluh ribu', 'sekitar 20 ribuan', 'kira-kira 20000', 'kurang lebih 20000'):
            with self.subTest(text=text):
                result = self.parser.parse(text)
                self.assertEqual(result.kind, 'approximate')
                self.assertEqual(result.soft_target, Decimal(20000))
                self.assertIsNone(result.constraint)
                self.assertIsNone(self.parser.parse_maximum(text))

    def test_ranges_use_decimal_and_en_dash_inherit_units(self) -> None:
        result = self.parser.parse('20–30 ribu')
        self.assertEqual((result.constraint.minimum, result.constraint.maximum), (Decimal(20000), Decimal(30000)))
        result = self.parser.parse('dua puluh sampai tiga puluh ribu')
        self.assertEqual((result.constraint.minimum,result.constraint.maximum),(Decimal(20000),Decimal(30000)))

    def test_hard_exclusive_limits_are_preserved(self) -> None:
        for text, field in (('di bawah sepuluh ribu','maximum'), ('di atas 10k','minimum')):
            bounds = self.parser.parse(text).constraint
            self.assertEqual(getattr(bounds,field), Decimal(10000))
            self.assertFalse(bounds.allows(Decimal(10000)))

    def test_person_count_is_separate_from_money(self) -> None:
        result = self.parser.parse('budget empat puluh ribu untuk 2 orang')
        self.assertEqual(result.amount, Decimal(40000))
        self.assertEqual(result.person_count, 2)
        self.assertEqual([m.role for m in result.numeric_roles], ['MONEY','PERSON_COUNT'])
        self.assertEqual([m.role for m in self.parser.numeric_roles('dua orang')], ['PERSON_COUNT'])
        request=self.parser.parse('budget empat puluh ribu untuk sepuluh orang')
        self.assertEqual(request.scope,'GROUP_TOTAL')
        self.assertEqual(request.person_count,10)
        request=self.parser.parse('budget empat puluh ribu untuk dua puluh lima orang')
        self.assertEqual(request.person_count,25)
        self.assertIsNone(request.constraint)

    def test_quantity_reference_time_table_measurement_and_rating_are_not_money(self) -> None:
        examples = {'pesan 2 es jeruk':'QUANTITY', 'meja nomor 20':'TABLE_NUMBER',
                    'jam 10':'TIME','menu ke 2':'REFERENCE','minuman 10000 ml':'MEASUREMENT',
                    'rating 4.5':'RATING'}
        for text, role in examples.items():
            with self.subTest(text=text):
                result = self.parser.parse(text)
                self.assertIsNone(result.constraint)
                self.assertEqual(result.numeric_roles[0].role,role)

    def test_personal_finance_does_not_become_order_budget(self) -> None:
        for text in ('uang bulananku 2 juta','gajiku dua juta','saldo 10000000','tabunganku Rp2.000.000'):
            result = self.parser.parse(text)
            self.assertEqual(result.kind,'none')
            self.assertEqual(result.numeric_roles[0].role,'PERSONAL_FINANCE')
        self.assertEqual(self.parser.parse_maximum('uang bulananku 2 juta tapi budget makan 20k'),20000)

    def test_fresh_bare_budget_is_marked_for_scope_clarification(self) -> None:
        self.assertTrue(self.parser.parse('budget 20k').scope_ambiguous)
        self.assertFalse(self.parser.parse('minuman 20k').scope_ambiguous)
        self.assertFalse(self.parser.parse('budget 20k per menu').scope_ambiguous)

    def test_invalid_and_ambiguous_inputs_never_create_soft_target(self) -> None:
        for text in ('sekitar 2 juta','minus sepuluh ribu','budget -20k','budget 30–20rb','sekitar -20k','makanan -20k'):
            with self.subTest(text=text):
                self.assertEqual(self.parser.parse(text).kind,'invalid')
        for text in ('sekitar 20k atau 30k','sekitar 20k untuk 2 orang', 'maksimal sekitar 20k'):
            result=self.parser.parse(text)
            self.assertIsNotNone(result.clarification)
            self.assertIsNone(result.soft_target)
            self.assertIsNone(result.constraint)

    def test_price_removal_retains_nonmonetary_roles(self) -> None:
        result = self.parser.without_prices('2 porsi maksimal sepuluh ribu')
        self.assertIn('2 porsi',result)
        self.assertNotIn('sepuluh',result)

    def test_literal_comparisons_are_distinct_from_previous_item_comparisons(self) -> None:
        for text in ('lebih murah dari 20k','lebih murah daripada dua puluh ribu'):
            bounds=self.parser.parse(text).constraint
            self.assertEqual(bounds.maximum,Decimal(20000))
            self.assertFalse(bounds.maximum_inclusive)
        bounds=self.parser.parse('lebih mahal dari 20k').constraint
        self.assertEqual(bounds.minimum,Decimal(20000))
        self.assertFalse(bounds.minimum_inclusive)
        self.assertEqual(self.parser.parse('lebih murah dari yang kedua').kind,'cheaper')


class SoftTargetStateTests(SimpleTestCase):
    def test_roundtrip_hash_and_optional_field(self) -> None:
        original=SearchConstraints(budget=BudgetConstraint(maximum=Decimal(15000)),soft_target=Decimal('20000.50'))
        restored=SearchConstraints.from_dict(original.to_dict())
        self.assertEqual(restored,original)
        self.assertEqual(hash(restored),hash(original))
        self.assertNotIn('soft_target',SearchConstraints().to_dict())
        self.assertFalse(original.budget.allows(Decimal(20000)))

    def test_soft_target_validation_rejects_nonfinite_negative_and_wrong_types(self) -> None:
        for value in ('NaN','Infinity','-1','1000001',20,None,True,'x'*33):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ConversationSession.validate_search({'soft_target':value})

    def test_schema4_lazy_upgrade_preserves_projection_graph_and_usage(self) -> None:
        session=SessionStore()
        state=ConversationSession(session)
        state.save_search(SearchConstraints(category='Minuman',budget=BudgetConstraint(maximum=Decimal(15000))))
        graph=state.contexts();graph['safety']['excluded_tags']=['shrimp']
        graph['overall']={'total_budget':'50000','explicitly_declared':True,'plan_id':1,'requested_categories':['Makanan','Minuman']}
        session[state.SCHEMA_KEY]=4;session[state.GEMINI_CALLS_KEY]=7;session[state.REVISION_KEY]=8
        old=deepcopy(graph);draft=state.draft()
        self.assertEqual(draft[state.SCHEMA_KEY],ConversationSession.SCHEMA_VERSION)
        self.assertEqual(draft[state.CONTEXTS_KEY],old)
        self.assertEqual(draft[state.GEMINI_CALLS_KEY],7)
        self.assertEqual(draft[state.REVISION_KEY],8)

    def test_schema4_cannot_claim_to_contain_a_soft_target(self) -> None:
        session=SessionStore();state=ConversationSession(session)
        state.contexts()['active']['constraints']['soft_target']='20000'
        session[state.SCHEMA_KEY]=4
        with self.assertRaises(ValueError):state.draft()
        with self.assertRaises(ConversationStoreUnavailable):ConversationStore._encode(dict(session))

    def test_signed_store_roundtrip_accepts_schema5_soft_target(self) -> None:
        session=SessionStore();state=ConversationSession(session)
        state.save_search(SearchConstraints(soft_target=Decimal(20000)))
        state.contexts();session[state.SCHEMA_KEY]=5
        decoded=ConversationStore._decode(ConversationStore._encode(dict(session)))
        self.assertEqual(decoded[state.SEARCH_KEY]['soft_target'],'20000')

    def test_root_soft_target_cannot_bypass_signed_state_validation(self) -> None:
        for value in (20, 'NaN', '-1'):
            session=SessionStore();session[ConversationSession.SCHEMA_KEY]=5
            session[ConversationSession.SEARCH_KEY]={'soft_target':value}
            with self.assertRaises(ConversationStoreUnavailable):ConversationStore._encode(dict(session))

    def test_pending_budget_rejects_wrong_shape_version_and_nonfinite_amount(self) -> None:
        for value in ({'amount':'NaN','context_id':1,'expires_at':9999999999},
                      {'amount':'20000','context_id':True,'expires_at':9999999999},
                      {'amount':'20000','context_id':1,'expires_at':9999999999,'extra':'x'}):
            with self.assertRaises(ValueError):ConversationSession.validate_pending_budget(value)
        session=SessionStore();state=ConversationSession(session);state.set_pending_budget(Decimal(20000))
        session[state.SCHEMA_KEY]=4
        with self.assertRaises(ConversationStoreUnavailable):ConversationStore._encode(dict(session))


class ApproximateBudgetIntegrationTests(TestCase):
    def setUp(self) -> None:
        self.food=Category.objects.create(name='Makanan')
        self.drinks=Category.objects.create(name='Minuman')
        self.items=[]
        for name,price in [('Pilihan Jauh',10000),('Pilihan Bawah',18000),('Pilihan Dekat',21000),('Pilihan Atas',23000),('Pilihan Mahal',40000)]:
            self.items.append(MenuItem.objects.create(name=name,price=price,category=self.food))
        self.drink=MenuItem.objects.create(name='Es Kelapa',price=10000,category=self.drinks)
        self.session=SessionStore();self.provider=NoBudgetProvider()

    def reply(self,text: str) -> dict:
        return ChatbotService(self.session,gemini_client=self.provider).reply(text)

    def prices(self,result: dict) -> list[Decimal]:
        return [match.item.price for match in result['recommendations']]

    def search(self) -> SearchConstraints:
        return ConversationSession(self.session).load_constraints()

    def test_around_target_ranks_both_sides_without_a_maximum(self) -> None:
        result=self.reply('makanan sekitar 20k')
        self.assertEqual(self.prices(result),[Decimal(21000),Decimal(18000),Decimal(23000)])
        self.assertIsNone(self.search().budget)
        self.assertIsNone(self.search().max_price)
        self.assertEqual(self.search().soft_target,Decimal(20000))
        self.assertIn('perkiraan',result['message'])

    def test_new_approximate_target_replaces_old_hard_range_as_user_chose(self) -> None:
        self.reply('makanan maksimal 15k')
        result=self.reply('sekitar 20k')
        self.assertGreater(self.prices(result)[0],Decimal(15000))
        self.assertIsNone(self.search().budget)
        self.assertIsNone(self.search().max_price)

    def test_new_hard_amount_replaces_soft_target_and_old_range(self) -> None:
        self.reply('makanan sekitar 20k')
        result=self.reply('maksimal 18k')
        self.assertTrue(all(price<=18000 for price in self.prices(result)))
        self.assertIsNone(self.search().soft_target)
        self.reply('di atas 5k')
        self.assertIsNone(self.search().budget.maximum)
        self.assertEqual(self.search().budget.minimum,Decimal(5000))

    def test_target_survives_alternatives_and_category_restore_but_not_new_scope(self) -> None:
        self.reply('makanan sekitar 20k')
        self.reply('yang lain')
        self.assertEqual(self.search().soft_target,Decimal(20000))
        self.reply('minuman')
        self.assertIsNone(self.search().soft_target)
        self.reply('balik ke makanan tadi')
        self.assertEqual(self.search().soft_target,Decimal(20000))

    def test_reset_clear_and_expiry_remove_target(self) -> None:
        for text in ('hapus batas budget','mulai lagi'):
            self.reply('makanan sekitar 20k');self.reply(text)
            self.assertIsNone(self.search().soft_target)
        self.reply('makanan sekitar 20k')
        with patch('recommendation.services.conversation_session.time',return_value=9999999999):
            ConversationSession(self.session).expire_dialog()
        self.assertIsNone(self.search().soft_target)

    def test_explicit_hard_limit_still_filters_when_target_is_present(self) -> None:
        bounds=SearchConstraints(category='Makanan',budget=BudgetConstraint(maximum=Decimal(18000)),soft_target=Decimal(20000))
        ranked=RecommendationService().rank(Preferences(),constraints=bounds)
        self.assertTrue(ranked)
        self.assertTrue(all(match.item.price<=18000 for match in ranked))

    def test_overall_budget_remains_hard_after_local_approximate_replacement(self) -> None:
        self.reply('budget total 20k')
        result=self.reply('makanan sekitar 23k')
        self.assertTrue(result['recommendations'])
        self.assertTrue(all(price<=20000 for price in self.prices(result)))
        self.assertEqual(ConversationSession(self.session).contexts()['overall']['total_budget'],'20000')

    def test_target_does_not_relax_hard_ingredient_exclusion(self) -> None:
        spicy=MenuTag.objects.create(name='spicy')
        self.items[2].tags.add(spicy)
        self.reply('makanan jangan pedas maksimal 15k')
        result=self.reply('sekitar 20k')
        self.assertNotIn(self.items[2].pk,{m.item.pk for m in result['recommendations']})
        self.assertIn('spicy',self.search().excluded_tags)

    def test_fresh_bare_budget_clarifies_without_setting_local_or_total_bounds(self) -> None:
        result=self.reply('budget 20k')
        self.assertFalse(result['recommendations'])
        self.assertIn('total',result['message'])
        self.assertIn('per menu',result['message'])
        self.assertIsNone(self.search().budget)
        self.assertFalse(ConversationSession(self.session).contexts()['overall'])
        result=self.reply('budget 20k per menu')
        self.assertTrue(result['recommendations'])
        self.assertEqual(self.search().budget.maximum,Decimal(20000))

    def test_bare_budget_with_active_food_context_is_per_menu(self) -> None:
        self.reply('makanan')
        self.reply('budget 20k')
        self.assertEqual(self.search().budget.maximum,Decimal(20000))

    def test_short_scope_answers_use_only_the_pending_nominal(self) -> None:
        self.reply('budget 20k');self.reply('per menu')
        self.assertEqual(self.search().budget.maximum,Decimal(20000))
        self.assertNotIn(ConversationSession.PENDING_BUDGET_KEY,self.session)
        self.session=SessionStore()
        self.reply('budget 20k');self.reply('total')
        self.assertEqual(ConversationSession(self.session).contexts()['overall']['total_budget'],'20000')
        self.assertIsNone(self.search().budget)

    def test_expired_pending_and_new_request_cannot_reuse_stale_nominal(self) -> None:
        self.reply('budget 20k')
        with patch('recommendation.services.conversation_session.time',return_value=9999999999):
            self.reply('per menu')
        self.assertIsNone(self.search().budget)
        self.session=SessionStore()
        self.reply('budget 20k');self.reply('minuman');self.reply('per menu')
        self.assertIsNone(self.search().budget)

    def test_pending_scope_is_session_owned_and_reset_clears_it(self) -> None:
        self.reply('budget 20k')
        other=ChatbotService(SessionStore(),gemini_client=self.provider)
        other.reply('per menu')
        self.assertIsNone(other._session_state.load_constraints().budget)
        self.reply('mulai lagi')
        self.assertNotIn(ConversationSession.PENDING_BUDGET_KEY,self.session)

    def test_exact_partial_with_approximate_price_clears_old_local_cap(self) -> None:
        self.reply('minuman maksimal 5k')
        result=self.reply('kelapa sekitar sepuluh ribu')
        self.assertEqual([m.item.pk for m in result['recommendations']],[self.drink.pk])
        self.assertIsNone(self.search().budget)
        self.assertEqual(self.search().soft_target,Decimal(10000))

    def test_personal_finance_preserves_existing_business_projection(self) -> None:
        self.reply('minuman maksimal 10k')
        before=self.search().to_dict()
        result=self.reply('uang bulananku 2 juta')
        self.assertFalse(result['recommendations'])
        self.assertEqual(self.search().to_dict(),before)
        self.assertNotIn('1.000.000',result['message'])

    def test_word_amounts_and_numbered_menu_names_remain_distinct(self) -> None:
        result=self.reply('makanan maksimal dua puluh ribu')
        self.assertEqual(set(self.prices(result)),{Decimal(10000),Decimal(18000)})
        numbered=MenuItem.objects.create(name='Paket 20',price=21000,category=self.food)
        self.session=SessionStore()
        result=self.reply('mau paket 20')
        self.assertEqual([m.item.pk for m in result['recommendations']],[numbered.pk])
        self.assertIsNone(self.search().budget)

    def test_approximate_total_and_multiple_amounts_clarify_without_changing_plan(self) -> None:
        self.reply('budget total 40k')
        before=deepcopy(ConversationSession(self.session).contexts()['overall'])
        for text in ('sekitar 20k untuk 2 orang','sekitar 20k atau 30k'):
            self.assertFalse(self.reply(text)['recommendations'])
            self.assertEqual(ConversationSession(self.session).contexts()['overall'],before)

    def test_http_exposes_additive_target_and_has_no_order_side_effect(self) -> None:
        with patch('recommendation.services.gemini.GeminiClient.generate',side_effect=AssertionError('No provider')):
            response=self.client.post('/api/recommendation/chat/',{'message':'makanan sekitar 20k'},content_type='application/json')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['active_search']['soft_target'],'20000')
        from orders.models import Order
        self.assertEqual(Order.objects.count(),0)

    def test_literal_comparison_requires_no_previous_anchor(self) -> None:
        result=self.reply('makanan lebih murah dari 20k')
        self.assertEqual(set(self.prices(result)),{Decimal(10000),Decimal(18000)})
