"""Explicit, opt-in recovery of legacy demo photos; never used by the storefront."""

from argparse import ArgumentParser
import json
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from menu.models import MenuItem

ASSET_ROOT = Path(__file__).resolve().parents[2] / "assets" / "recovered-menu"


class Command(BaseCommand):
    help = (
        "Preview missing legacy menu photos. Writes require --apply; existing photos are preserved."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--apply", action="store_true")
        mode.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--detail-only",
            action="store_true",
            help="Recover optional landscape detail photos only.",
        )

    def handle(self, *args: object, **options: object) -> None:
        entries = json.loads((ASSET_ROOT / "manifest.json").read_text(encoding="utf-8"))["photos"]
        failed = 0

        for entry in entries:
            name = entry["name"]
            field_name = "detail_image" if options["detail_only"] else "image"
            source_key = "detail_webp" if options["detail_only"] else "webp"

            if not entry.get(source_key):
                self.stdout.write(f"SKIP {name}: no recovered {field_name} asset")
                continue

            # Names are only legacy import identifiers, never runtime image rules.
            try:
                with transaction.atomic():
                    matches = list(MenuItem.objects.select_for_update().filter(name=name))

                    if len(matches) != 1:
                        self.stdout.write(
                            f"SKIP {name}: {len(matches)} matches; requires manual resolution"
                        )
                        continue

                    item = matches[0]

                    if getattr(item, field_name):
                        self.stdout.write(f"SKIP {name}: existing photo preserved")
                        continue

                    source = ASSET_ROOT / entry[source_key]
                    data = source.read_bytes()

                    if not options["apply"]:
                        self.stdout.write(
                            f"DRY-RUN {name}: would attach {source.name} ({len(data)} bytes)"
                        )
                        continue

                    getattr(item, field_name).save(source.name, ContentFile(data), save=False)
                    item.save(update_fields=[field_name, "updated_at"])
                    self.stdout.write(f"OK {name}: photo attached")
            except Exception as exc:
                failed += 1
                # Do not disclose storage credentials or delete a possibly shared file.
                self.stderr.write(
                    f"FAIL {name}: {type(exc).__name__}; check storage/database, retained files are not deleted"
                )

        if failed:
            raise CommandError(
                f"{failed} photo(s) failed; successful items can safely be skipped on rerun."
            )
