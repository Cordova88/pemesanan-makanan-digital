"""Bounded menu photo processing shared by forms and model saves."""

from django.core.files.base import File
import io
import warnings
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_EDGE = 10000
FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
HELP_TEXT = "JPEG, PNG, atau WebP; maksimal 10 MB dan 20 juta piksel. Foto transparan memberi hasil floating terbaik."


class PreparedPhoto(ContentFile):
    """Processed public image together with its private original metadata."""

    def __init__(
        self,
        content: bytes | str,
        name: str | None = None,
        *,
        original_bytes: bytes = b"",
        original_name: str = "",
    ) -> None:
        super().__init__(content, name=name)
        self.original_bytes: bytes = original_bytes
        self.original_name: str = original_name


def prepare_photo(upload: File) -> PreparedPhoto:
    if isinstance(upload, PreparedPhoto):
        return upload

    if getattr(upload, "size", 0) > MAX_BYTES:
        raise ValidationError("Ukuran foto maksimal 10 MB.", code="photo_size")

    upload.seek(0)
    raw = upload.read(MAX_BYTES + 1)
    upload.seek(0)

    if len(raw) > MAX_BYTES:
        raise ValidationError("Ukuran foto maksimal 10 MB.", code="photo_size")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)

            with Image.open(io.BytesIO(raw), formats=list(FORMATS)) as probe:
                kind = probe.format

                if kind not in FORMATS:
                    raise ValidationError("Gunakan foto JPEG, PNG, atau WebP.", code="photo_format")

                width, height = probe.size

                if width * height > MAX_PIXELS or max(width, height) > MAX_EDGE:
                    raise ValidationError(
                        "Foto maksimal 20 juta piksel dan 10.000 piksel per sisi.",
                        code="photo_dimensions",
                    )

                if getattr(probe, "n_frames", 1) != 1:
                    raise ValidationError(
                        "Gunakan foto diam, bukan gambar animasi.", code="photo_animation"
                    )

                probe.verify()

            with Image.open(io.BytesIO(raw), formats=list(FORMATS)) as source:
                source.load()
                oriented = ImageOps.exif_transpose(source)
                mode = (
                    "RGBA"
                    if "A" in oriented.getbands() or "transparency" in oriented.info
                    else "RGB"
                )
                photo = oriented.convert(mode)
                photo.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
                # Do not carry EXIF, comments, or other source metadata into public media.
                photo.info.clear()
                output = io.BytesIO()
                photo.save(output, format="WEBP", quality=85, method=6)
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValidationError(
            "Foto rusak atau tidak aman diproses. Unggah foto lain.", code="photo_invalid"
        ) from exc

    identity = uuid4().hex

    return PreparedPhoto(
        output.getvalue(),
        name=f"{identity}.webp",
        original_bytes=raw,
        original_name=f"{identity}.{FORMATS[kind]}",
    )


def archive_original(photo: PreparedPhoto) -> None:
    """Private archive, deliberately outside MEDIA_ROOT and its public URL."""
    root = Path(
        getattr(
            settings, "MENU_ORIGINALS_ROOT", Path(settings.BASE_DIR) / "private" / "menu-originals"
        )
    )
    media = Path(settings.MEDIA_ROOT).resolve()

    if root.resolve() == media or media in root.resolve().parents:
        raise ValidationError("Lokasi arsip foto harus berada di luar media publik.")

    storage = FileSystemStorage(
        location=root, file_permissions_mode=0o600, directory_permissions_mode=0o700
    )
    storage.save(photo.original_name, ContentFile(photo.original_bytes))
