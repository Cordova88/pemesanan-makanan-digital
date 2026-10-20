"""Phase 4 tag operations, catalog vocabulary and deterministic filtering."""
from decimal import Decimal
import json
from unittest.mock import patch

from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import SimpleTestCase, TestCase

from menu.models import Category, MenuItem, MenuTag, MenuTagAlias
from ..services.chatbot import ChatbotService
from ..services.conversation_session import ConversationSession
from ..services.conversation_interpreter import ConversationInterpreter, PreferenceOperation, ConversationInterpretation
from ..services.mood_resolver import MoodResolver
from ..services.recommendation import RecommendationService, SearchConstraints
from ..services.tag_extractor import Preferences, TagExtractor
from ..services.text_generator import TextGenerator


class UnavailableTagGenerator(TextGenerator):
    def __init__(self) -> None:
        self.calls: int = 0

    def generate(self, prompt: str) -> str | None:
        self.calls += 1
        return None


class TagSemanticsTests(SimpleTestCase):
    def setUp(self) -> None:
        self.extractor = TagExtractor()

    def test_degree_and_dislike_are_soft_but_bans_are_hard(self) -> None:
        for text in ('jangan terlalu pedas', 'tidak terlalu pedas', 'aku kurang suka pedas', 'tidak terlalu suka yang pedas'):
            with self.subTest(text=text):
                result = self.extractor.extract(text)
                self.assertIn('spicy', result.soft_excluded_tags)
                self.assertNotIn('spicy', result.excluded_tags | result.tags)
                self.assertNotIn('mild', result.tags)
        for text in ('jangan pedas', 'tanpa sambal', 'tidak mau pedas'):
            self.assertIn('spicy', self.extractor.extract(text).excluded_tags)

    def test_negation_scope_handles_lists_and_positive_clause(self) -> None:
        result = self.extractor.extract('tanpa ayam dan udang, mau sapi')
        self.assertTrue({'chicken', 'shrimp'} <= result.excluded_tags)
        self.assertIn('beef', result.tags)
        self.assertNotIn('beef', result.excluded_tags)
        result = self.extractor.extract('kurang suka ayam dan udang')
        self.assertTrue({'chicken', 'shrimp'} <= result.soft_excluded_tags)
        self.assertFalse(result.excluded_tags)

    def test_last_mention_corrects_old_polarity(self) -> None:
        result = self.extractor.extract('jangan ayam, sekarang mau ayam')
        self.assertIn('chicken', result.tags)
        self.assertNotIn('chicken', result.excluded_tags)
        result = self.extractor.extract('mau ayam, tapi jangan ayam')
        self.assertIn('chicken', result.excluded_tags)

    def test_compound_aliases_do_not_require_opposites(self) -> None:
        for text in ('tidak berkuah', 'tanpa kuah'):
            result = self.extractor.extract(text)
            self.assertIn('dry', result.tags)
            self.assertNotIn('brothy', result.tags)
        result = self.extractor.extract('tidak pedas')
        self.assertIn('spicy', result.excluded_tags)
        self.assertNotIn('spicy', result.tags)

    def test_dish_type_does_not_invent_taste_or_filling(self) -> None:
        for text, tags in (('nasi goreng', {'fried_rice', 'rice'}), ('mie goreng', {'fried_noodle', 'noodle'})):
            result = self.extractor.extract(text)
            self.assertTrue(tags <= result.tags)
            self.assertFalse({'savory', 'filling'} & result.tags)

    def test_targeted_correction_preserves_other_preferences(self) -> None:
        interpreter = ConversationInterpreter(self.extractor)
        preferences = Preferences(tags={'rice', 'chicken'}, excluded_tags={'shrimp'})
        delta = interpreter.interpret('gak jadi ayam, mau sapi')
        preferences.apply_interpretation(delta, MoodResolver())
        self.assertEqual(preferences.tags, {'rice', 'beef'})
        self.assertEqual(preferences.excluded_tags, {'shrimp'})
        self.assertNotIn('CLEAR', [op.action for op in delta.operations])
        for text in ('gak jadi ayam mau sapi', 'tidak jadi ayam ingin sapi'):
            delta = interpreter.interpret(text)
            self.assertEqual(delta.operations[0], PreferenceOperation('REPLACE', ('beef',), ('chicken',)))

    def test_drop_is_not_exclude_and_relax_is_not_add(self) -> None:
        preferences = Preferences(tags={'rice', 'chicken'}, excluded_tags={'shrimp'}, soft_excluded_tags={'spicy'})
        preferences.apply_interpretation(ConversationInterpretation('REMOVE_PREFERENCES', operations=[
            PreferenceOperation('DROP', ('chicken',)), PreferenceOperation('RELAX', ('shrimp', 'spicy')),
        ]), MoodResolver())
        self.assertEqual(preferences.tags, {'rice'})
        self.assertFalse(preferences.excluded_tags | preferences.soft_excluded_tags)
        delta = ConversationInterpreter(self.extractor).interpret('gak jadi ayam')
        self.assertEqual(delta.operations[0], PreferenceOperation('DROP', ('chicken',)))

    def test_clear_tags_does_not_clear_mood_or_affordable(self) -> None:
        preferences = Preferences(tags={'chicken'}, excluded_tags={'shrimp'}, moods={'tired'}, prefer_affordable=True)
        preferences.apply_interpretation(ConversationInterpretation('REMOVE_PREFERENCES', operations=[PreferenceOperation('CLEAR_TAGS')]), MoodResolver())
        self.assertFalse(preferences.tags | preferences.excluded_tags)
        self.assertEqual(preferences.moods, {'tired'})
        self.assertTrue(preferences.prefer_affordable)

    def test_dynamic_aliases_are_instance_scoped_and_deduplicated(self) -> None:
        self.extractor.configure_catalog_tags([('herbal', 'Herbal')], [('herbal', 'rempah alami'), ('herbal', 'rempah alami')])
        self.assertEqual(self.extractor.extract('rempah alami').tags, {'herbal'})
        self.assertIn('herbal', self.extractor.extract('jangan rempah alami').excluded_tags)
        self.assertNotIn('herbal', TagExtractor().get_allowed_tags())


class CatalogTagIntegrationTests(TestCase):
    def setUp(self) -> None:
        self.category = Category.objects.create(name='Makanan')
        self.tags = {name: MenuTag.objects.create(name=name, display_name=label) for name, label in (
            ('rice', 'Nasi'), ('chicken', 'Ayam'), ('beef', 'Sapi'), ('shrimp', 'Udang'),
            ('spicy', 'Pedas'), ('oily', 'Berminyak'), ('herbal', 'Rempah'), ('fried_rice', 'Nasi goreng'),
        )}
        self.items = {}
        for name, price, names in (
            ('Ayam A', 18000, ('rice', 'chicken', 'spicy', 'oily')),
            ('Ayam B', 19000, ('rice', 'chicken')),
            ('Sapi A', 22000, ('rice', 'beef')),
            ('Udang A', 15000, ('rice', 'shrimp', 'spicy')),
            ('Rempah A', 16000, ('rice', 'herbal')),
            ('Nasi Goreng Khusus', 17000, ('fried_rice', 'rice')),
        ):
            item = MenuItem.objects.create(name=name, category=self.category, price=Decimal(price))
            item.tags.add(*(self.tags[tag] for tag in names))
            self.items[name] = item
        MenuTagAlias.objects.create(tag=self.tags['herbal'], phrase='wangi rempah')
        MenuTagAlias.objects.create(tag=self.tags['herbal'], phrase='aroma lama', is_active=False)
        self.session = SessionStore()
        self.generator = UnavailableTagGenerator()

    def reply(self, text: str, *, more: bool = False) -> dict:
        return ChatbotService(self.session, gemini_client=self.generator).reply(text, more=more)

    def test_cms_alias_new_tag_and_inactive_alias(self) -> None:
        result = self.reply('ingin wangi rempah')
        self.assertEqual([m.item.pk for m in result['recommendations']], [self.items['Rempah A'].pk])
        service = ChatbotService(self.session, gemini_client=self.generator)
        self.assertNotIn('herbal', service.tag_extractor.extract('aroma lama').tags)

    def test_replacement_keeps_rice_budget_and_shrimp_ban(self) -> None:
        self.reply('nasi ayam maksimal 25 ribu')
        self.reply('jangan udang')
        result = self.reply('gak jadi ayam, mau sapi')
        stored = self.session['recommendation_state']
        self.assertTrue({'rice', 'beef'} <= set(stored['tags']))
        self.assertNotIn('chicken', stored['tags'])
        self.assertIn('shrimp', stored['excluded_tags'])
        self.assertEqual(result['active_search']['budget']['maximum'], '25000')
        self.assertEqual([m.item.name for m in result['recommendations']], ['Sapi A'])

    def test_degree_penalizes_instead_of_filtering_spicy(self) -> None:
        self.reply('nasi maksimal 25 ribu')
        result = self.reply('jangan terlalu pedas')
        names = [m.item.name for m in result['recommendations']]
        self.assertNotIn('spicy', self.session['recommendation_state']['excluded_tags'])
        self.assertIn('spicy', self.session['recommendation_state']['soft_excluded_tags'])
        matches = RecommendationService().rank(Preferences(tags={'rice'}, soft_excluded_tags={'spicy'}), limit=20)
        scores = {m.item.name: m.score for m in matches}
        self.assertEqual(scores['Ayam B'] - scores['Ayam A'], 2)
        self.assertIn('Ayam A', scores)
        self.assertTrue(names)

    def test_hard_ban_filters_and_relax_restores_without_required_tag(self) -> None:
        self.reply('nasi maksimal 25 ribu')
        result = self.reply('jangan udang')
        self.assertNotIn('Udang A', [m.item.name for m in result['recommendations']])
        self.assertFalse(any('tanpa' in reason.casefold() for m in result['recommendations'] for reason in m.match_reasons))
        self.assertNotIn('tanpa', result['message'].casefold())
        self.reply('boleh udang lagi')
        self.assertNotIn('shrimp', self.session['recommendation_state']['excluded_tags'])
        self.assertNotIn('shrimp', self.session['recommendation_search']['required_tags'])
        self.assertEqual(self.session['recommendation_search']['budget']['maximum'], '25000')

    def test_drop_removes_required_tag_without_banning_and_clear_keeps_budget(self) -> None:
        self.reply('nasi ayam maksimal 20 ribu')
        self.reply('hapus preferensi ayam')
        self.assertNotIn('chicken', self.session['recommendation_search']['required_tags'])
        self.assertNotIn('chicken', self.session['recommendation_state']['excluded_tags'])
        result = self.reply('hapus semua tag')
        self.assertFalse(self.session['recommendation_state']['tags'])
        self.assertFalse(result['active_search']['required_tags'])
        self.assertEqual(result['active_search']['budget']['maximum'], '20000')
        self.assertTrue(all(m.item.price <= 20000 for m in result['recommendations']))

    def test_clear_without_budget_does_not_leave_stale_preferences(self) -> None:
        self.reply('ayam')
        self.reply('hapus semua tag')
        self.assertFalse(self.session['recommendation_state']['tags'])

    def test_catalog_oily_reference_is_local_and_preserves_bounds(self) -> None:
        self.reply('nasi ayam maksimal 25 ribu')
        previous_calls = self.generator.calls
        result = self.reply('yang tadi terlalu berminyak')
        self.assertIn('oily', self.session['recommendation_state']['soft_excluded_tags'])
        self.assertEqual(result['active_search']['budget']['maximum'], '25000')
        self.assertEqual(self.generator.calls, previous_calls)
        self.assertEqual(result['recommendations'][0].item.name, 'Ayam B')

    def test_unavailable_inactive_category_and_price_never_leak(self) -> None:
        self.items['Ayam B'].is_available = False
        self.items['Ayam B'].save(update_fields=['is_available'])
        self.items['Ayam A'].is_active = False
        self.items['Ayam A'].save(update_fields=['is_active'])
        result = self.reply('nasi ayam maksimal 20 ribu')
        self.assertFalse(result['recommendations'])
        self.category.is_active = False
        self.category.save(update_fields=['is_active'])
        self.assertFalse(self.reply('nasi maksimal 25 ribu')['recommendations'])

    def test_allergy_does_not_infer_safety_from_missing_tag_or_call_provider(self) -> None:
        for text in ('aku alergi udang, ingin nasi', 'ada menu bebas alergen?', 'saya allergic seafood'):
            before = dict(self.session)
            calls = self.generator.calls
            result = self.reply(text)
            self.assertFalse(result['recommendations'])
            self.assertIn('staf', result['message'])
            self.assertNotIn('aman untuk', result['message'])
            self.assertEqual(self.generator.calls, calls)
            safety = self.session[ConversationSession.CONTEXTS_KEY]['safety']
            self.assertTrue(safety['verification_required'])
            self.assertIn('shrimp', safety['excluded_tags'])

    def test_more_does_not_repeat_shown_items_or_ignore_hard_exclusions(self) -> None:
        self.reply('nasi maksimal 25 ribu')
        first = self.reply('jangan udang')
        ids = {m.item.pk for m in first['recommendations']}
        second = self.reply('yang lain', more=True)
        self.assertFalse(ids & {m.item.pk for m in second['recommendations']})
        self.assertTrue(all('shrimp' not in set(m.item.tags.values_list('name', flat=True)) for m in second['recommendations']))

    def test_dish_with_no_assumed_taste_still_matches_catalog(self) -> None:
        result = self.reply('nasi goreng maksimal 20 ribu')
        self.assertEqual([m.item.name for m in result['recommendations']], ['Nasi Goreng Khusus'])

    def test_ai_cannot_relax_hard_exclusion_without_explicit_user_change(self) -> None:
        self.reply('nasi maksimal 25 ribu')
        self.reply('jangan udang')
        data = {
            'intent': 'RECOMMEND', 'add_tags': ['shrimp'], 'remove_tags': [],
            'excluded_tags': [], 'soft_excluded_tags': [], 'moods': [],
            'clear_moods': False, 'max_price': None, 'prefer_affordable': None,
            'clear_max_price': False, 'clear_prefer_affordable': False, 'message_is_meaningful': True,
        }
        with patch.object(self.generator, 'generate', return_value=json.dumps(data)):
            result = self.reply('yang tadi terlalu eneg')
        self.assertIn('shrimp', self.session['recommendation_state']['excluded_tags'])
        self.assertNotIn('shrimp', self.session['recommendation_state']['tags'])
        self.assertFalse(any(m.item.name == 'Udang A' for m in result['recommendations']))

    def test_degree_does_not_require_mild_tag_missing_from_catalog(self) -> None:
        self.reply('nasi maksimal 25 ribu')
        result = self.reply('tidak terlalu pedas')
        self.assertTrue(result['recommendations'])
        self.assertNotIn('mild', result['active_search']['required_tags'])
