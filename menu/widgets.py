from django.core.files.base import File
from django import forms


class MenuPhotoWidget(forms.ClearableFileInput):
    template_name = "menu/widgets/photo_input.html"

    class Media:
        css = {"all": ("menu/css/menu-card.css?v=images-p8", "menu/css/photo-editor.css?v=phase9")}
        js = ("menu/js/photo-editor.js?v=phase9",)

    def get_context(
        self,
        name: str,
        value: File | None,
        attrs: dict[str, object] | None,
    ) -> dict[str, object]:
        context = super().get_context(name, value, attrs)
        context["widget"]["photo_url"] = value.url if value and hasattr(value, "url") else ""
        return context
