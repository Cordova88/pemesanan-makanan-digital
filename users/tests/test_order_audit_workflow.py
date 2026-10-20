from datetime import timedelta
from urllib.parse import parse_qs
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from orders.models import AuditLog, Order, Payment, Table


class CMSOrderAuditWorkflowTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user('audit-review', is_staff=True)
        self.client.force_login(self.staff)
        self.table = Table.objects.create(number='Teras Uji')
        self.pending = Order.objects.create(public_id='P15PENDING', customer_name='Pelanggan Satu',
            order_type='DINE_IN', table=self.table, expires_at=timezone.now() - timedelta(hours=2), total=28000)
        self.paid = Order.objects.create(public_id='P15PAID', customer_name='Pelanggan Dua',
            order_type='TAKEAWAY', status='PAID', total=15000)
        self.system = AuditLog.objects.create(order=self.pending, action=AuditLog.Action.CREATED)
        self.actor = AuditLog.objects.create(order=self.paid, action=AuditLog.Action.PAID, actor=self.staff, actor_role='ADMIN')
        self.orders = reverse('staff:orders')
        self.audit = reverse('staff:audit-log')

    def test_order_search_by_id_customer_table_and_combined_filters(self):
        for q in (' p15pending ', 'Satu', 'teras'):
            response = self.client.get(self.orders, {'q': q, 'status': 'PENDING', 'type': 'DINE_IN', 'period': 'today'})
            self.assertEqual(list(response.context['orders']), [self.pending])
            self.assertContains(response, 'Reset')
            self.assertContains(response, 'value="PENDING" selected')
            self.assertContains(response, 'value="DINE_IN" selected')
        response = self.client.get(self.orders, {'q': 'Satu', 'status': 'PAID'})
        self.assertContains(response, 'Tidak ada pesanan yang cocok')

    def test_badges_match_model_status_and_links_reach_audit(self):
        response = self.client.get(self.orders)
        self.assertContains(response, 'text-bg-success">Paid')
        self.assertContains(response, 'text-bg-warning">Pending')
        self.assertContains(response, self.audit + '?q=' + self.pending.public_id)
        for status in ('CANCELLED', 'EXPIRED', 'REFUNDED'):
            self.paid.status = status
            self.paid.save()
            response = self.client.get(self.orders)
            style = 'text-bg-secondary' if status == 'REFUNDED' else 'text-bg-danger'
            self.assertContains(response, style + '">' + self.paid.get_status_display())

    def test_audit_search_action_role_system_and_order_link(self):
        for query in ('p15paid', 'Dua', 'audit-review'):
            response = self.client.get(self.audit, {'q': query, 'action': 'ORDER_PAID', 'period': 'today'})
            self.assertEqual(list(response.context['logs']), [self.actor])
            self.assertContains(response, 'ADMIN')
            self.assertContains(response, self.orders + '?q=' + self.paid.public_id)
        self.assertContains(self.client.get(self.audit, {'q': 'p15pending'}), 'Sistem')
        self.assertContains(self.client.get(self.audit, {'q': 'missing'}), 'Tidak ada catatan yang cocok')

    def test_invalid_filters_are_ignored_and_removed_from_pagination_query(self):
        for url in (self.orders, self.audit):
            response = self.client.get(url, {'status': 'bad', 'type': 'bad', 'action': 'bad', 'period': 'bad', 'unused': 'x'})
            self.assertFalse(response.context['filtered'])
            self.assertEqual(response.context['querystring'], '')
            self.assertEqual(response.context['total'], 2)

    def test_order_pagination_preserves_filters_and_invalid_page_is_safe(self):
        for index in range(28):
            Order.objects.create(public_id=f'PAGE15{index:04d}', customer_name='Batch & Uji', order_type='TAKEAWAY', status='PAID')
        filters = {'q': 'Batch & Uji', 'status': 'PAID', 'type': 'TAKEAWAY', 'period': 'today'}
        first = self.client.get(self.orders, filters)
        second = self.client.get(self.orders, {**filters, 'page': 2})
        self.assertEqual(first.context['total'], 28)
        self.assertEqual(len(first.context['orders']), 25)
        self.assertEqual(len(second.context['orders']), 3)
        self.assertEqual(parse_qs(second.context['querystring']), {key: [value] for key, value in filters.items()})
        self.assertTrue(set(first.context['orders']).isdisjoint(set(second.context['orders'])))
        self.assertEqual(self.client.get(self.orders, {**filters, 'page': 'nonsense'}).context['page_obj'].number, 1)

    def test_audit_pagination_reaches_records_older_than_previous_150_limit(self):
        AuditLog.objects.bulk_create([AuditLog(order=self.pending, action=AuditLog.Action.MODIFIED) for _ in range(155)])
        response = self.client.get(self.audit, {'q': self.pending.public_id, 'period': 'today', 'page': 7})
        self.assertEqual(response.context['total'], 156)
        self.assertEqual(len(response.context['logs']), 6)
        self.assertIn(self.system, response.context['logs'])
        self.assertEqual(parse_qs(response.context['querystring']), {'q': [self.pending.public_id], 'period': ['today']})

    def test_period_filters_use_local_today_and_last_seven_days(self):
        current = timezone.now()
        old = current - timedelta(days=8)
        Order.objects.filter(pk=self.paid.pk).update(created_at=old)
        AuditLog.objects.filter(pk=self.actor.pk).update(created_at=old)
        with patch('users.views.timezone.now', return_value=current):
            for period in ('today', '7'):
                self.assertEqual(list(self.client.get(self.orders, {'period': period}).context['orders']), [self.pending])
                self.assertEqual(list(self.client.get(self.audit, {'period': period}).context['logs']), [self.system])

    def test_lists_do_not_expire_orders_write_audit_or_process_payments(self):
        before = list(Order.objects.order_by('pk').values('pk', 'status', 'updated_at', 'total'))
        log_count = AuditLog.objects.count()
        for url in (self.orders, self.audit):
            self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(list(Order.objects.order_by('pk').values('pk', 'status', 'updated_at', 'total')), before)
        self.assertEqual(AuditLog.objects.count(), log_count)
        self.assertEqual(Payment.objects.count(), 0)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, 'PENDING')

    def test_non_staff_cannot_read_orders_or_audit(self):
        self.client.force_login(get_user_model().objects.create_user('audit-ordinary'))
        for url in (self.orders, self.audit):
            self.assertEqual(self.client.get(url).status_code, 302)
