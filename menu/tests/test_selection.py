from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from cart.services import CartService
from django.contrib.sessions.backends.signed_cookies import SessionStore
from ..image_processing import PreparedPhoto, prepare_photo
from ..models import AddOn, Category, MenuItem, VariantGroup, VariantOption
from ..selection import MenuSelection


class MenuSelectionTests(TestCase):
    def setUp(self) -> None:
        category = Category.objects.create(name="Food")
        self.item = MenuItem.objects.create(category=category, name="Rice", price=Decimal("10.50"))
        self.group = VariantGroup.objects.create(menu_item=self.item, name="Size", is_required=True)
        self.option = VariantOption.objects.create(group=self.group, name="Large", price_adjustment=Decimal("2.25"))
        self.addon = AddOn.objects.create(name="Sauce", price=Decimal("0.75"))
        self.addon.menu_items.add(self.item)

    def test_resolved_selection_calculates_server_decimal_price(self) -> None:
        selection = MenuSelection.from_ids(self.item, [self.option.pk], [self.addon.pk])
        self.assertEqual(selection.unit_price, Decimal("13.50"))
        self.assertEqual(selection.options, (self.option,))
        self.assertEqual(selection.addons, (self.addon,))
        with self.assertRaises(AttributeError):
            selection.options = ()

    def test_duplicate_requested_ids_keep_existing_order_semantics(self) -> None:
        selection = MenuSelection.from_ids(self.item, [self.option.pk] * 2, [self.addon.pk] * 2)
        self.assertEqual(len(selection.options), 1)
        self.assertEqual(len(selection.addons), 1)
        self.assertEqual(selection.unit_price, Decimal("13.50"))

    def test_required_and_invalid_options_preserve_distinct_order_messages(self) -> None:
        for ids, message in (
            ([], "Select exactly one option for every required variant group."),
            ([999999], "Invalid variant selection."),
        ):
            with self.subTest(ids=ids), self.assertRaises(ValidationError) as raised:
                MenuSelection.from_ids(self.item, ids)
            self.assertEqual(raised.exception.messages, [message])

    def test_multiple_options_per_group_and_inactive_addons_are_rejected(self) -> None:
        second = VariantOption.objects.create(group=self.group, name="Small")
        with self.assertRaises(ValidationError):
            MenuSelection.from_ids(self.item, [self.option.pk, second.pk])
        self.addon.is_active = False
        self.addon.save()
        with self.assertRaises(ValidationError) as raised:
            MenuSelection.from_ids(self.item, [self.option.pk], [self.addon.pk])
        self.assertEqual(raised.exception.messages, ["Invalid add-on selection."])

    def test_cart_keeps_its_original_localized_error_contract(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            CartService(SessionStore()).add_item(self.item.pk, 1)
        self.assertEqual(raised.exception.messages, ["Pilih satu opsi untuk setiap varian wajib."])
        with self.assertRaises(ValidationError) as raised:
            CartService(SessionStore()).add_item(self.item.pk, 1, [self.option.pk], [999999])
        self.assertEqual(raised.exception.messages, ["Tambahan tidak tersedia untuk menu ini."])


class PreparedPhotoConstructorTests(SimpleTestCase):
    def test_constructor_preserves_file_behavior_original_metadata_and_idempotency(self) -> None:
        photo = PreparedPhoto(b"processed", "photo.webp", original_bytes=b"original", original_name="photo.png")
        self.assertEqual(photo.read(), b"processed")
        self.assertEqual(photo.size, 9)
        self.assertEqual(photo.original_bytes, b"original")
        self.assertEqual(photo.original_name, "photo.png")
        self.assertIs(prepare_photo(photo), photo)
