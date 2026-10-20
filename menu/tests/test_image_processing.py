import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings

from menu.forms import MenuPhotoForm
from menu.image_processing import MAX_BYTES, prepare_photo
from menu.models import Category, MenuItem
from users.forms import MenuItemForm


def upload(kind="PNG", size=(40, 20), alpha=True):
    stream = io.BytesIO()
    image = Image.new(
        "RGBA" if alpha and kind != "JPEG" else "RGB",
        size,
        (180, 40, 20, 100) if alpha and kind != "JPEG" else (180, 40, 20),
    )
    image.save(stream, kind)

    return SimpleUploadedFile("../../photo.bin", stream.getvalue(), "application/octet-stream")


class PhotoProcessingTests(SimpleTestCase):
    def test_content_detection_formats_and_transparency(self):
        for kind in ("JPEG", "PNG", "WEBP"):
            with self.subTest(kind=kind):
                result = prepare_photo(upload(kind))

                with Image.open(result) as photo:
                    self.assertEqual(photo.format, "WEBP")
                    self.assertEqual(photo.size, (40, 20))
                    self.assertEqual(photo.mode, "RGB" if kind == "JPEG" else "RGBA")

                    if kind != "JPEG":
                        self.assertEqual(photo.getchannel("A").getextrema(), (100, 100))

    def test_corrupt_svg_and_gif_rejected(self):
        for data in (
            b"not an image",
            b'<svg xmlns="http://www.w3.org/2000/svg"/>',
            upload("GIF", alpha=False).read(),
            upload().read()[:40],
        ):
            with self.assertRaises(ValidationError):
                prepare_photo(SimpleUploadedFile("photo.png", data))

    def test_file_size_limit(self):
        with self.assertRaisesMessage(ValidationError, "10 MB"):
            prepare_photo(SimpleUploadedFile("large.png", b"x" * (MAX_BYTES + 1)))

    def test_animated_webp_is_rejected(self):
        data = io.BytesIO()
        Image.new("RGB", (10, 10), "red").save(
            data,
            "WEBP",
            save_all=True,
            append_images=[Image.new("RGB", (10, 10), "blue")],
            duration=100,
            loop=0,
        )

        with self.assertRaisesMessage(ValidationError, "foto diam"):
            prepare_photo(SimpleUploadedFile("animated.webp", data.getvalue()))

    def test_dimensions_checked_before_decode(self):
        with patch("menu.image_processing.MAX_PIXELS", 100):
            with self.assertRaises(ValidationError):
                prepare_photo(upload(size=(20, 20)))

    def test_resize_no_upscale_and_exif_orientation(self):
        source = Image.new("RGB", (2000, 1000), "red")
        exif = Image.Exif()
        exif[274] = 6
        data = io.BytesIO()
        source.save(data, "JPEG", exif=exif)
        result = prepare_photo(SimpleUploadedFile("photo.jpg", data.getvalue()))

        with Image.open(result) as photo:
            self.assertEqual(photo.size, (640, 1280))
            self.assertFalse(photo.getexif())

    def test_each_replacement_has_unique_safe_name(self):
        first, second = prepare_photo(upload()), prepare_photo(upload())
        self.assertNotEqual(first.name, second.name)
        self.assertRegex(first.name, r"^[a-f0-9]{32}\.webp$")

    def test_read_is_bounded_even_if_size_metadata_is_incorrect(self):
        file = SimpleUploadedFile("fake.jpg", b"x" * (MAX_BYTES + 1))
        file.size = 0

        with self.assertRaisesMessage(ValidationError, "10 MB"):
            prepare_photo(file)

    def test_maximum_edge_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, "10.000"):
            prepare_photo(upload(size=(10001, 1)))


class PhotoIntegrationTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        settings = override_settings(
            MEDIA_ROOT=self.root / "media", MENU_ORIGINALS_ROOT=self.root / "originals"
        )
        settings.enable()
        self.addCleanup(settings.disable)
        self.category = Category.objects.create(name="Makanan")
        self.data = {
            "name": "Sate Ayam",
            "category": self.category.pk,
            "price": "24000",
            "is_active": True,
            "is_available": True,
        }

    def test_both_forms_optimize_and_archive_originals(self):
        self.assertIs(admin.site._registry[MenuItem].form, MenuPhotoForm)

        for form_class in (MenuPhotoForm, MenuItemForm):
            before = len(list(self.root.rglob("*")))
            file = upload()
            original = file.read()
            file.seek(0)
            form = form_class(self.data, {"image": file})
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(len(list(self.root.rglob("*"))), before)
            item = form.save()
            self.assertTrue(item.image.name.endswith(".webp"))
            self.assertIn(original, [p.read_bytes() for p in (self.root / "originals").iterdir()])

            with item.image.open("rb") as saved, Image.open(saved) as decoded:
                self.assertEqual(decoded.format, "WEBP")

    def test_invalid_upload_is_form_error_without_storage_writes(self):
        for form_class in (MenuPhotoForm, MenuItemForm):
            form = form_class(self.data, {"image": SimpleUploadedFile("bad.png", b"invalid")})
            self.assertFalse(form.is_valid())
            self.assertIn("image", form.errors)

        self.assertEqual(list(self.root.iterdir()), [])

    def test_replace_keep_clear_and_api_url(self):
        form = MenuItemForm(self.data, {"image": upload()})
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save()
        first = item.image.name
        form = MenuItemForm(self.data, instance=item)
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save()
        self.assertEqual(item.image.name, first)
        form = MenuItemForm(self.data, {"image": upload("JPEG")}, instance=item)
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save()
        self.assertNotEqual(item.image.name, first)
        self.assertTrue(item.image.storage.exists(first))
        self.assertEqual(
            self.client.get("/api/menu/").json()["items"][0]["image_url"], item.image.url
        )
        form = MenuItemForm({**self.data, "image-clear": "on"}, instance=item)
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save()
        self.assertFalse(item.image)
        self.assertEqual(self.client.get("/api/menu/").json()["items"][0]["image_url"], "")
        self.assertEqual(len(list((self.root / "originals").iterdir())), 2)

    def test_direct_model_upload_also_processed(self):
        item = MenuItem.objects.create(category=self.category, name="New", price=1, image=upload())
        self.assertTrue(item.image.name.endswith(".webp"))
        self.assertEqual(len(list((self.root / "originals").iterdir())), 1)

    def test_private_archive_cannot_be_configured_inside_public_media(self):
        with override_settings(MENU_ORIGINALS_ROOT=self.root / "media" / "originals"):
            with self.assertRaisesMessage(ValidationError, "di luar media publik"):
                MenuItem.objects.create(
                    category=self.category, name="Unsafe", price=1, image=upload()
                )

        self.assertEqual(MenuItem.objects.count(), 0)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_storage_names_are_generated_and_archive_has_no_public_route(self):
        item = MenuItem.objects.create(category=self.category, name="Uji", price=1, image=upload())
        self.assertRegex(item.image.name, r"^menu/[a-f0-9]{32}\.webp$")
        original = next((self.root / "originals").iterdir())
        self.assertRegex(original.name, r"^[a-f0-9]{32}\.png$")
        self.assertEqual(
            self.client.get("/private/menu-originals/" + original.name).status_code, 404
        )
