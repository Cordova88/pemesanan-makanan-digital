from django.contrib.auth.models import AnonymousUser, Group, User
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from orders.permissions import cashier_required
from ..access import StaffAccess
from ..views import _cms_user, _home_for, _is_cashier


class StaffAccessTests(TestCase):
    def test_anonymous_and_regular_users_keep_no_staff_access(self) -> None:
        for user in (AnonymousUser(), User.objects.create_user("regular-policy-test")):
            policy = StaffAccess(user)
            self.assertFalse(policy.can_manage_catalog)
            self.assertFalse(policy.can_use_cashier)
            self.assertFalse(policy.is_cashier)
            self.assertEqual(policy.home_route, "storefront")
            with self.assertRaises(PermissionDenied):
                cashier_required(user)

    def test_admin_and_cashier_keep_distinct_roles_and_home_routes(self) -> None:
        admin = User.objects.create_user("admin-policy-test", is_staff=True)
        cashier = User.objects.create_user("cashier-policy-test")
        cashier.groups.add(Group.objects.create(name="Cashier"))
        self.assertTrue(_cms_user(admin))
        self.assertFalse(_is_cashier(admin))
        self.assertEqual(_home_for(admin), "staff:dashboard")
        self.assertFalse(_cms_user(cashier))
        self.assertTrue(_is_cashier(cashier))
        self.assertEqual(_home_for(cashier), "kasir:dashboard")
        cashier_required(admin)
        cashier_required(cashier)

    def test_policy_reads_role_changes_instead_of_caching_old_permissions(self) -> None:
        user = User.objects.create_user("changing-policy-test")
        policy = StaffAccess(user)
        self.assertFalse(policy.is_cashier)
        user.groups.add(Group.objects.create(name="Cashier"))
        self.assertTrue(policy.is_cashier)
        self.assertTrue(policy.can_use_cashier)
