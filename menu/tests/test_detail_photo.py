from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from menu.models import MenuItem
from menu.tests import test_image_processing as photo_tests
from users.forms import MenuItemForm


upload = photo_tests.upload


class DetailPhotoTests(TestCase):
    setUp = photo_tests.PhotoIntegrationTests.setUp
    def test_detail_upload_keeps_cutout_and_has_its_own_api_url(self):
        form = MenuItemForm(self.data, {"image": upload(), "detail_image": upload("JPEG", size=(80, 40))})
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save()
        self.assertNotEqual(item.image.name, item.detail_image.name)
        self.assertTrue(item.detail_image.name.startswith("menu/detail/"))
        payload = self.client.get("/api/menu/").json()["items"][0]
        self.assertEqual(payload["image_url"], item.image.url)
        self.assertEqual(payload["detail_image_url"], item.detail_image.url)
        original_cutout = item.image.name
        form = MenuItemForm({**self.data, "detail_image-clear": "on"}, instance=item)
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save()
        self.assertFalse(item.detail_image)
        self.assertEqual(item.image.name, original_cutout)
        self.assertEqual(self.client.get("/api/menu/").json()["items"][0]["detail_image_url"], "")

    def test_invalid_detail_upload_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        form = MenuItemForm(self.data, {"detail_image": SimpleUploadedFile("bad.png", b"bad", "image/png")})
        self.assertFalse(form.is_valid())
        self.assertIn("detail_image", form.errors)
        self.assertEqual(MenuItem.objects.count(), 0)

    def test_cms_can_upload_detail_independently(self):
        user = get_user_model().objects.create(username="detail-test", is_staff=True)
        self.client.force_login(user)
        item = MenuItem.objects.create(category=self.category, name="Sate Ayam", price=24000, image="menu/cutout.webp")
        response = self.client.post(reverse("staff:menu-item-edit", args=[item.pk]), {**self.data, "detail_image": upload("JPEG")})
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.image.name, "menu/cutout.webp")
        self.assertTrue(item.detail_image)

    def test_home_reserves_dynamic_artwork_without_landscape_photos(self):
        response = self.client.get("/")
        self.assertContains(response, 'id="homeHero"')
        self.assertNotContains(response, "beranda-hero.webp")
        self.assertNotContains(response, "beranda-hero.jpg")
        self.assertNotContains(response, "ayam-detail.svg")
