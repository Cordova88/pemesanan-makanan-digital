"""H5 optional expression task: one call, minimal packet and atomic validation."""
from decimal import Decimal
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from menu.models import MenuItem, VariantGroup, VariantOption

from ..services.ai.explanations import RecommendationExplanationService
from ..services.chatbot import ChatbotService
from . import test_v3_planning as fixtures


@override_settings(CHATBOT_AI_RESPONSE_MODE='wording', CHATBOT_AI_WORDING_ENABLED=True,
                   CHATBOT_SEMANTIC_RERANKING_ENABLED=True, GEMINI_MAX_CALLS_PER_SESSION=50)
class GroundedWordingTests(TestCase):
    setUp = fixtures.ResponsePlanningTests.setUp
    plan = fixtures.ResponsePlanningTests.plan
    def reply(self, text: str = 'enak buat nemenin nugas minuman maksimal 20k') -> dict:
        return ChatbotService(self.session, gemini_client=self.provider).reply(text)

    def ids(self, result: dict) -> list[int]:
        return [m.item.pk for m in result['recommendations']]

    def test_wording_mode_spends_only_one_call_without_semantic_reranking(self) -> None:
        result = self.reply()
        self.assertEqual(len(self.provider.calls), 1)
        self.assertFalse(self.provider.calls[0].startswith('Rank the supplied'))
        self.assertEqual(self.ids(result), [self.a.pk, self.b.pk])
        self.assertTrue(result['message'].startswith(self.provider.intro))
        self.assertIn('Rp20.000', result['message'])

    def test_minimal_packet_excludes_numbers_context_and_private_descriptions(self) -> None:
        self.session.update({'cart': {'note': 'CART_PRIVATE'}, '_auth_user_id': 'AUTH_PRIVATE'})
        self.reply()
        prompt = self.provider.calls[0]
        for private in ('CART_PRIVATE','AUTH_PRIVATE','DESCRIPTION_PRIVATE','nugas','max_price',
                        'verified_plan_minimum','minimum_payable','quantity','moods','requested_tags'):
            self.assertNotIn(private, prompt)
        self.assertIn('catalog_tags', prompt)
        self.assertIn('match_reasons', prompt)

    def test_local_actions_and_health_context_never_spend_wording_call(self) -> None:
        for text in ('halo','minuman 20k','yang es alpha','yang pertama','aku alergi udang',
                     'enak buat nemenin nugas saya depresi'):
            self.reply(text)
        self.assertEqual(self.provider.calls, [])

    def test_wording_disabled_does_not_fall_back_to_another_provider_task(self) -> None:
        with override_settings(CHATBOT_AI_WORDING_ENABLED=False):
            result = self.reply()
        self.assertTrue(result['recommendations'])
        self.assertEqual(self.provider.calls, [])

    def test_unknown_mode_is_local_without_a_speculative_task(self) -> None:
        with override_settings(CHATBOT_AI_RESPONSE_MODE='invalid'):
            self.reply()
        self.assertEqual(self.provider.calls, [])

    def test_timeout_uses_local_results_and_charges_one_attempt(self) -> None:
        def fail() -> None:
            raise TimeoutError('PRIVATE_TIMEOUT')
        self.provider.on_wording = fail
        result = self.reply()
        self.assertEqual(self.ids(result), [self.a.pk,self.b.pk])
        self.assertEqual(len(self.provider.calls), 1)
        self.assertEqual(self.session['gemini_calls'], 1)
        self.assertNotIn('PRIVATE_TIMEOUT', result['message'])

    def test_quota_refusal_preserves_local_cards(self) -> None:
        self.session['gemini_calls'] = 50
        self.assertEqual(self.ids(self.reply()), [self.a.pk,self.b.pk])
        self.assertEqual(self.provider.calls, [])

    def test_invalid_intro_rejects_even_an_otherwise_valid_explanation(self) -> None:
        self.provider.raw = json.dumps({'intro':'Stok tersedia', 'explanations':[
            {'id':self.a.pk,'text':'Es Alpha sesuai dengan Minuman.'}]})
        self.assertEqual(RecommendationExplanationService(self.provider).from_plan(
            self.plan(),self.matches,self.preferences),(None,{}))

    def test_one_unsupported_explanation_rejects_the_entire_proposal(self) -> None:
        for bad in ('Es Beta sehat.', 'Es Beta harga Rp1.', 'Es Beta tersedia.', '<b>Es Beta</b>'):
            self.provider.raw = json.dumps({'intro':self.provider.intro,'explanations':[
                {'id':self.a.pk,'text':'Es Alpha sesuai dengan Minuman.'}, {'id':self.b.pk,'text':bad}]})
            self.assertEqual(RecommendationExplanationService(self.provider).from_plan(
                self.plan(),self.matches,self.preferences),(None,{}))

    def test_intro_cannot_turn_a_catalog_tag_into_an_unsupported_claim(self) -> None:
        self.provider.raw = json.dumps({'intro':'Ini pilihan minuman.', 'explanations':[]})
        self.assertEqual(RecommendationExplanationService(self.provider).from_plan(
            self.plan(),self.matches,self.preferences),(None,{}))

    def test_price_or_required_option_change_invalidates_wording(self) -> None:
        self.provider.on_wording = lambda: MenuItem.objects.filter(pk=self.b.pk).update(price=Decimal('25000'))
        result = self.reply()
        self.assertEqual(self.ids(result),[self.a.pk])
        self.assertFalse(result['message'].startswith(self.provider.intro))
        self.assertEqual(len(self.provider.calls),1)

    def test_same_price_required_option_change_invalidates_wording(self) -> None:
        group = VariantGroup.objects.create(menu_item=self.a,name='Wajib',is_required=True)
        VariantOption.objects.create(group=group,name='Awal')
        self.provider.on_wording = lambda: VariantOption.objects.create(group=group,name='Baru')
        result = self.reply()
        self.assertEqual(self.ids(result),[self.a.pk,self.b.pk])
        self.assertFalse(result['message'].startswith(self.provider.intro))

    def test_repeated_intro_uses_local_opening_and_keeps_only_fingerprints(self) -> None:
        first,second = self.reply(),self.reply()
        self.assertTrue(first['message'].startswith(self.provider.intro))
        self.assertFalse(second['message'].startswith(self.provider.intro))
        self.assertEqual(len(self.provider.calls),2)
        self.assertNotIn(self.provider.intro,json.dumps(dict(self.session)))

    def test_warnings_and_budget_text_are_retained_after_generated_intro(self) -> None:
        result = self.reply()
        self.assertIn('Rp20.000',result['message'])
        self.assertIn('varian',result['message'])
        self.assertIn('belum bisa kupastikan',result['message'])
        self.assertNotIn('bersifat subjektif',result['message'])

    def test_supported_catalog_explanation_is_accepted(self) -> None:
        self.provider.raw = json.dumps({'intro':self.provider.intro,'explanations':[
            {'id':self.a.pk,'text':'Es Alpha sesuai dengan Minuman.'}]})
        intro,text = RecommendationExplanationService(self.provider).from_plan(
            self.plan(),self.matches,self.preferences)
        self.assertEqual(intro,self.provider.intro)
        self.assertEqual(text,{self.a.pk:'Es Alpha sesuai dengan Minuman.'})

    def test_bad_wire_vectors_are_atomic_and_never_retry(self) -> None:
        for raw in ('{', '{"intro":"Ini pilihan","intro":"Menu palsu","explanations":[]}',
                    '{"intro":NaN,"explanations":[]}',
                    json.dumps({'intro':self.provider.intro,'explanations':[{'id':99999,'text':'Menu palsu'}]}),
                    json.dumps({'intro':self.provider.intro,'explanations':[],'action':'checkout'}),
                    '😀'*16001):
            with self.subTest(raw=raw[:60]):
                self.provider.raw = raw
                before = len(self.provider.calls)
                result = self.reply()
                self.assertEqual(len(self.provider.calls),before+1)
                self.assertEqual(self.ids(result),[self.a.pk,self.b.pk])
                self.assertFalse(result['message'].startswith(self.provider.intro))

    def test_unavailable_menu_is_removed_after_wording_call(self) -> None:
        self.provider.on_wording = lambda: MenuItem.objects.filter(pk=self.a.pk).update(is_available=False)
        result = self.reply()
        self.assertEqual(self.ids(result),[self.b.pk])
        self.assertFalse(result['message'].startswith(self.provider.intro))
        self.assertEqual(len(self.provider.calls),1)

    def test_stale_preflight_skips_explanation_consumer(self) -> None:
        service = ChatbotService(self.session,gemini_client=self.provider)
        plan = self.plan()
        MenuItem.objects.filter(pk=self.a.pk).update(is_available=False)
        with patch.object(service.explanation_service,'from_plan') as generate:
            fresh,intro,text,unchanged = service._wording_for_plan(
                plan,self.matches,self.preferences,self.constraints)
        generate.assert_not_called()
        self.assertEqual([m.item.pk for m in fresh],[self.b.pk])
        self.assertIsNone(intro)
        self.assertEqual(text,{})
        self.assertFalse(unchanged)

    def test_disclosure_distinguishes_local_and_optional_gemini(self) -> None:
        with patch('google.genai.Client',side_effect=AssertionError('No SDK for page render')):
            for enabled,expected in ((False,'Mode lokal aktif. Pesan tidak dikirim ke Gemini.'),
                                     (True,'Sebagian pesan dapat dikirim ke Google Gemini')):
                with override_settings(GEMINI_ENABLED=enabled):
                    response = self.client.get('/chatbot/')
                self.assertEqual(response.status_code,200)
                self.assertContains(response,expected)
                self.assertContains(response,'Pemesanan tetap melalui keranjang.')

    def test_packet_copy_has_no_user_preference_or_plan_metadata(self) -> None:
        plan = self.plan()
        packet = plan.wording_packet()
        self.assertEqual(set(packet),{'purpose','tone','items','selected_menu_ids','allowed_claims'})
        self.assertTrue(all(set(row)=={'id','name','category','catalog_tags','match_reasons'}
                            for row in packet['items']))
        packet['items'][0]['catalog_tags'].clear()
        self.assertTrue(plan.wording_packet()['items'][0]['catalog_tags'])
