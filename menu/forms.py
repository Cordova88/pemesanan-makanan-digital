from django.core.files.base import File
from django import forms

from .image_processing import HELP_TEXT, prepare_photo
from .models import MenuItem
from .widgets import MenuPhotoWidget


class MenuPhotoForm(forms.ModelForm):
    # Validate dimensions before Pillow decodes the full uploaded image.
    image = forms.FileField(
        required=False,
        label="Gambar menu",
        help_text=HELP_TEXT,
        widget=MenuPhotoWidget(
            attrs={"accept": "image/jpeg,image/png,image/webp", "data-menu-image-input": ""}
        ),
        error_messages={"empty": "Foto kosong. Pilih foto lain."},
    )
    detail_image = forms.FileField(
        required=False,
        label="Foto lama (arsip opsional)",
        help_text="Foto arsip tidak digunakan pada halaman pelanggan. Beranda dan pilihan menu memakai Gambar menu dengan blob otomatis. JPEG, PNG, WebP; maksimal 10 MB dan 20 juta piksel.",
        widget=MenuPhotoWidget(
            attrs={"accept": "image/jpeg,image/png,image/webp", "data_photo_kind": "detail"}
        ),
        error_messages={"empty": "Foto kosong. Pilih foto lain."},
    )

    class Meta:
        model = MenuItem
        fields = "__all__"

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields["image"].widget.attrs["data_menu_id"] = self.instance.pk or ""
        self.fields["detail_image"].widget.attrs["data_menu_id"] = self.instance.pk or ""

    def clean_image(self) -> File | bool | None:
        return self._clean_photo("image")

    def clean_detail_image(self) -> File | bool | None:
        return self._clean_photo("detail_image")

    def _clean_photo(self, field_name: str) -> File | bool | None:
        image = self.cleaned_data.get(field_name)

        if not image or not hasattr(image, "content_type"):
            return image

        return prepare_photo(image)
