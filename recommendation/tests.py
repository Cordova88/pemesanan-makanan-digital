from decimal import Decimal
from django.test import TestCase
from menu.models import Category, MenuItem, MenuTag
from .services.recommendation import RecommendationService
from .services.tag_extractor import Preferences, TagExtractor

class RecommendationTests(TestCase):
    def setUp(self):
        category=Category.objects.create(name='Makanan')
        self.spicy=MenuTag.objects.create(name='spicy'); chicken=MenuTag.objects.create(name='chicken'); rice=MenuTag.objects.create(name='rice')
        self.best=MenuItem.objects.create(category=category,name='Ayam Geprek',price=Decimal('15000'))
        self.best.tags.add(self.spicy,chicken,rice)
        self.other=MenuItem.objects.create(category=category,name='Mie Pedas',price=Decimal('14000')); self.other.tags.add(self.spicy)
        self.off=MenuItem.objects.create(category=category,name='Tidak Ada',price=Decimal('10000'),is_available=False); self.off.tags.add(self.spicy)
    def test_tag_relationship_and_extraction(self):
        self.assertIn(self.spicy, self.best.tags.all())
        self.assertEqual(TagExtractor().extract('Aku mau AyAm PEDAS dan nasi').tags, {'chicken','spicy','rice'})
    def test_ranking_price_and_exclusion(self):
        service=RecommendationService(); found=service.recommend(Preferences({'spicy','chicken','rice'},20000))
        self.assertEqual(found[0],self.best); self.assertNotIn(self.off,found)
        self.assertNotIn(self.best,service.recommend(Preferences({'spicy'},20000),exclude_ids=[self.best.id]))
    def test_chat_and_cart_api(self):
        response=self.client.post('/api/recommendation/chat/', data='{"message":"mau ayam pedas nasi"}', content_type='application/json')
        self.assertEqual(response.status_code,200); self.assertEqual(response.json()['recommendations'][0]['id'],self.best.id)
        response=self.client.post('/api/recommendation/add/', data='{"menu_item_id": %s, "quantity": 1, "variant_ids": [], "addon_ids": []}' % self.best.id, content_type='application/json')
        self.assertEqual(response.status_code,200); self.assertEqual(len(self.client.get('/api/cart/').json()['items']),1)

    def test_reset_clears_chat_preferences_and_recommendation_history(self):
        response = self.client.post(
            '/api/recommendation/chat/',
            data='{"message":"Aku mau makanan pedas"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.client.session['recommendation_state']['tags'])
        self.assertTrue(self.client.session['recommendation_shown'])

        response = self.client.post(
            '/api/recommendation/chat/',
            data='{"message":"mulai lagi"}',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['state'], 'COLLECTING_PREFERENCES')
        self.assertEqual(response.json()['preferences']['tags'], [])
        self.assertEqual(response.json()['recommendations'], [])
        self.assertNotIn('recommendation_state', self.client.session)
        self.assertNotIn('recommendation_shown', self.client.session)
