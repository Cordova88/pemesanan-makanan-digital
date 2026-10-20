import io
import tempfile
from pathlib import Path

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from menu.models import Category, MenuItem


def photo(kind="PNG"):
    stream = io.BytesIO()
    Image.new("RGB" if kind == "JPEG" else "RGBA", (48, 32), "red").save(stream, kind)
    return SimpleUploadedFile("food." + kind.lower(), stream.getvalue(), "image/" + kind.lower())


class PhotoEditorEndpointTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        setting = override_settings(MEDIA_ROOT=self.root / "media", MENU_ORIGINALS_ROOT=self.root / "originals")
        setting.enable()
        self.addCleanup(setting.disable)
        user = get_user_model().objects.create(username="photo-test", is_staff=True, is_superuser=True)
        self.client.force_login(user)
        self.category = Category.objects.create(name="Makanan")

    def data(self, **extra):
        return {"category": self.category.pk, "name": "Sate Ayam", "description": "Bumbu kacang", "price": "24000", "is_active": "on", "is_available": "on", **extra}

    def test_cms_add_and_edit_have_shared_preview_and_guidance(self):
        item = MenuItem.objects.create(category=self.category, name="Uji", price=1, image="menu/existing.webp")
        for url in [reverse("staff:menu-items"), reverse("staff:menu-item-edit", args=[item.pk])]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "data-photo-editor")
            self.assertContains(response, "photo-editor.js")
            self.assertContains(response, "Card dan blob dibuat otomatis")
            self.assertContains(response, "maksimal 10 MB")
            self.assertContains(response, "data-photo-selection")
            self.assertContains(response, "Foto arsip")
            self.assertNotContains(response, "Gunakan foto landscape")

    def test_cms_upload_replace_keep_and_clear(self):
        add_url = reverse("staff:menu-items")
        response = self.client.post(add_url, self.data(image=photo()))
        self.assertEqual(response.status_code, 302)
        item = MenuItem.objects.get(name="Sate Ayam")
        first = item.image.name
        self.assertTrue(first.endswith(".webp"))
        edit_url = reverse("staff:menu-item-edit", args=[item.pk])
        response = self.client.post(edit_url, self.data())
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.image.name, first)
        response = self.client.post(edit_url, self.data(image=photo("JPEG")))
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertNotEqual(item.image.name, first)
        self.assertTrue(item.image.storage.exists(first))
        self.assertContains(self.client.get(edit_url), item.image.url)
        self.assertEqual(self.client.post(edit_url, self.data(**{"image-clear": "on"})).status_code, 302)
        item.refresh_from_db()
        self.assertFalse(item.image)
        self.assertEqual(len(list((self.root / "originals").iterdir())), 2)

    def test_replacing_customer_photo_preserves_legacy_archive(self):
        item = MenuItem.objects.create(category=self.category, name="Original", price=1,
                                       image="menu/original.webp", detail_image="menu/detail/archive.webp")
        response = self.client.post(reverse("staff:menu-item-edit", args=[item.pk]), self.data(image=photo()))
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertNotEqual(item.image.name, "menu/original.webp")
        self.assertEqual(item.detail_image.name, "menu/detail/archive.webp")
        payload = self.client.get("/api/menu/").json()["items"][0]
        self.assertEqual(payload["image_url"], item.image.url)

    def test_admin_upload_and_preview(self):
        response = self.client.get(reverse("admin:menu_menuitem_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-photo-editor")
        self.assertContains(response, "photo-editor.js")
        self.assertEqual(self.client.post(reverse("admin:menu_menuitem_add"), self.data(image=photo("WEBP"), _save="Save")).status_code, 302)
        item = MenuItem.objects.get(name="Sate Ayam")
        self.assertTrue(item.image.name.endswith(".webp"))
        edit_url = reverse("admin:menu_menuitem_change", args=[item.pk])
        self.assertContains(self.client.get(edit_url), item.image.url)
        previous = item.image.name
        self.assertEqual(self.client.post(edit_url, self.data(image=photo(), _save="Save")).status_code, 302)
        item.refresh_from_db()
        self.assertNotEqual(item.image.name, previous)
        self.assertEqual(self.client.post(edit_url, self.data(**{"image-clear": "on", "_save": "Save"})).status_code, 302)
        item.refresh_from_db()
        self.assertFalse(item.image)

    def test_invalid_file_returns_error_in_both_paths(self):
        for url in [reverse("staff:menu-items"), reverse("admin:menu_menuitem_add")]:
            response = self.client.post(url, self.data(image=SimpleUploadedFile("bad.png", b"corrupt", "image/png")))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Foto rusak")
        self.assertEqual(MenuItem.objects.count(), 0)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_clear_and_upload_conflict_preserves_existing_photo(self):
        item = MenuItem.objects.create(category=self.category, name="Original", price=1, image="menu/original.webp")
        response = self.client.post(reverse("staff:menu-item-edit", args=[item.pk]), self.data(image=photo(), **{"image-clear": "on"}))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("image"))
        item.refresh_from_db()
        self.assertEqual(item.image.name, "menu/original.webp")
