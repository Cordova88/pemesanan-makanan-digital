import hashlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, SimpleTestCase, override_settings

from menu.management.commands.backfill_menu_images import ASSET_ROOT
from menu.models import Category, MenuItem


class RecoveredAssetTests(SimpleTestCase):
    def test_four_photos_are_valid_transparent_and_smaller(self):
        entries = json.loads((ASSET_ROOT / "manifest.json").read_text(encoding="utf-8"))["photos"]
        self.assertEqual(len(entries), 4)

        for entry in entries:
            with self.subTest(name=entry["name"]):
                raw = (ASSET_ROOT / entry["source_png"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["source_sha256"])

                with Image.open(io.BytesIO(raw)) as original, Image.open(
                    ASSET_ROOT / entry["webp"]
                ) as photo:
                    self.assertEqual(original.size, (1254, 1254))
                    self.assertEqual(photo.format, "WEBP")
                    self.assertEqual(photo.size, (960, 960))
                    self.assertEqual(photo.mode, "RGBA")
                    original.thumbnail((960, 960), Image.Resampling.LANCZOS)
                    self.assertEqual(
                        photo.getchannel("A").tobytes(), original.getchannel("A").tobytes()
                    )
                    self.assertLess(entry["webp_bytes"], len(raw))


class BackfillPhotoTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings = override_settings(MEDIA_ROOT=self.media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.category = Category.objects.create(name="Makanan")
        self.item = MenuItem.objects.create(category=self.category, name="Ayam Geprek", price=18000)

    def run_command(self, **options):
        output = io.StringIO()
        call_command("backfill_menu_images", stdout=output, stderr=output, **options)

        return output.getvalue()

    def test_default_is_read_only(self):
        self.assertIn("DRY-RUN Ayam Geprek", self.run_command())
        self.item.refresh_from_db()
        self.assertFalse(self.item.image)
        self.assertEqual(list(Path(self.media.name).rglob("*")), [])

    def test_apply_then_rerun_preserves_file_and_reference(self):
        self.assertIn("OK Ayam Geprek", self.run_command(apply=True))
        self.item.refresh_from_db()
        filename = self.item.image.name
        self.assertTrue(self.item.image.storage.exists(filename))
        before = list(Path(self.media.name).rglob("*.webp"))
        self.assertIn("existing photo preserved", self.run_command(apply=True))
        self.item.refresh_from_db()
        self.assertEqual(self.item.image.name, filename)
        self.assertEqual(before, list(Path(self.media.name).rglob("*.webp")))

    def test_existing_admin_reference_is_never_overwritten(self):
        self.item.image = "menu/admin-upload.png"
        self.item.save(update_fields=["image"])
        self.run_command(apply=True)
        self.item.refresh_from_db()
        self.assertEqual(self.item.image.name, "menu/admin-upload.png")

    def test_duplicate_names_are_skipped(self):
        MenuItem.objects.create(category=self.category, name=self.item.name, price=20000)
        self.assertIn("2 matches", self.run_command(apply=True))
        self.assertFalse(MenuItem.objects.exclude(image="").exists())

    def test_unmatched_names_are_not_guessed(self):
        self.item.name = "Ayam Geprek Spesial"
        self.item.save(update_fields=["name"])
        self.assertIn("0 matches", self.run_command(apply=True))
        self.item.refresh_from_db()
        self.assertFalse(self.item.image)

    def test_storage_failure_is_reported_without_database_update(self):
        with patch(
            "django.db.models.fields.files.FieldFile.save",
            side_effect=OSError("storage unavailable"),
        ):
            with self.assertRaises(CommandError):
                self.run_command(apply=True)

        self.item.refresh_from_db()
        self.assertFalse(self.item.image)
