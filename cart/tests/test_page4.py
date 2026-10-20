import json
from django.test import TestCase
from menu.models import AddOn, Category, MenuItem, VariantGroup, VariantOption
from orders.models import Order


class PageFourFlowTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Makanan")
        self.item = MenuItem.objects.create(name="Ayam Geprek", category=category, price=18000)
        group = VariantGroup.objects.create(menu_item=self.item, name="Level pedas", is_required=True)
        self.medium = VariantOption.objects.create(group=group, name="Sedang")
        self.hot = VariantOption.objects.create(group=group, name="Pedas")
        self.egg = AddOn.objects.create(name="Telur", price=5000)
        self.item.allowed_addons.add(self.egg)

    def add(self, note="Sambal dipisah, ya."):
        response = self.client.post('/api/cart/add/', data=json.dumps({
            'menu_item_id': self.item.id, 'quantity': 1,
            'variant_ids': [self.medium.id], 'addon_ids': [self.egg.id], 'note': note,
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        return response.json()['items'][-1]['id']

    def test_kitchen_notes_survive_checkout_and_refresh(self):
        self.add()
        response = self.client.post('/api/orders/checkout/', data=json.dumps({
            'customer_name': 'Pelanggan Uji', 'order_type': 'TAKEAWAY',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(public_id=response.json()['public_id'])
        self.assertEqual(order.total, 23000)
        self.assertIn('Ayam Geprek × 1: Sambal dipisah, ya.', order.note)
        saved = self.client.get(f'/api/orders/{order.public_id}/').json()
        self.assertEqual(saved['items'][0]['variants'], [{'name':'Sedang'}])
        self.assertEqual(saved['items'][0]['addons'], [{'name':'Telur'}])
        self.assertEqual(self.client.get('/api/cart/').json()['items'], [])

    def test_edit_updates_configuration_and_server_price(self):
        line = self.add()
        response = self.client.patch(f'/api/cart/{line}/',data=json.dumps({
            'quantity':2, 'variant_ids':[self.hot.id], 'addon_ids':[], 'note':'Tanpa telur',
        }),content_type='application/json')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['total'],'36000.00')
        self.assertEqual(response.json()['items'][0]['note'],'Tanpa telur')

    def test_different_kitchen_notes_remain_separate(self):
        self.add('Sambal dipisah')
        self.add('Sambal dicampur')
        self.assertEqual(len(self.client.get('/api/cart/').json()['items']),2)

    def test_invalid_edit_preserves_previous_line(self):
        line=self.add()
        response=self.client.patch(f'/api/cart/{line}/',data=json.dumps({
            'quantity':2,'variant_ids':[],'addon_ids':[],'note':'Tidak boleh tersimpan',
        }),content_type='application/json')
        self.assertEqual(response.status_code,400)
        saved=self.client.get('/api/cart/').json()
        self.assertEqual(saved['total'],'23000.00')
        self.assertEqual(saved['items'][0]['note'],'Sambal dipisah, ya.')

    def test_oversized_note_rejected(self):
        response=self.client.post('/api/cart/add/',data=json.dumps({
            'menu_item_id':self.item.id,'quantity':1,'variant_ids':[self.medium.id],
            'addon_ids':[],'note':'x'*501,
        }),content_type='application/json')
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.get('/api/cart/').json()['items'],[])
