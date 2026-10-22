from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse


class LogoutSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('dummy-staff', is_staff=True)
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        self.url = reverse('staff:logout')

    def test_get_cannot_logout_an_authenticated_user(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)

    def test_post_without_csrf_token_cannot_logout(self):
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.assertIn('_auth_user_id', self.client.session)

    def test_both_navigation_surfaces_render_csrf_protected_logout_and_post_works(self):
        for route in ('staff:dashboard', 'kasir:dashboard'):
            response = self.client.get(reverse(route))
            self.assertContains(response, f'action="{self.url}"')
            self.assertContains(response, 'name="csrfmiddlewaretoken"')
            self.assertNotContains(response, f'href="{self.url}"')
        token = self.client.cookies['csrftoken'].value
        response = self.client.post(self.url, {'csrfmiddlewaretoken': token})
        self.assertRedirects(response, reverse('staff:login'))
        self.assertNotIn('_auth_user_id', self.client.session)
