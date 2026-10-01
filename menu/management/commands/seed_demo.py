from decimal import Decimal
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from menu.models import AddOn, Category, MenuItem, VariantGroup, VariantOption
from orders.models import Table
class Command(BaseCommand):
    help="Create development admin, cashier, and Indonesian menu sample data."
    def handle(self,*args,**kwargs):
        cashiers,_=Group.objects.get_or_create(name="Cashier")
        admin,_=User.objects.get_or_create(username="admin",defaults={"is_staff":True,"is_superuser":True})
        if not admin.has_usable_password(): admin.set_password("admin12345"); admin.save()
        cashier,_=User.objects.get_or_create(username="cashier")
        if not cashier.has_usable_password(): cashier.set_password("cashier12345"); cashier.save()
        cashier.groups.add(cashiers)
        foods,_=Category.objects.get_or_create(name="Makanan"); drinks,_=Category.objects.get_or_create(name="Minuman")
        nasi,_=MenuItem.objects.get_or_create(name="Nasi Goreng",category=foods,defaults={"price":Decimal("15000.00"),"description":"Nasi goreng spesial"})
        MenuItem.objects.get_or_create(name="Ayam Geprek",category=foods,defaults={"price":Decimal("15000.00")})
        MenuItem.objects.get_or_create(name="Es Teh",category=drinks,defaults={"price":Decimal("5000.00")})
        group,_=VariantGroup.objects.get_or_create(menu_item=nasi,name="Ukuran",defaults={"is_required":True})
        VariantOption.objects.get_or_create(group=group,name="Regular",defaults={"price_adjustment":0})
        VariantOption.objects.get_or_create(group=group,name="Large",defaults={"price_adjustment":Decimal("4000.00")})
        for name,price in (("Extra Sambal","3000.00"),("Extra Cheese","5000.00")):
            addon,_=AddOn.objects.get_or_create(name=name,defaults={"price":Decimal(price)}); addon.menu_items.add(nasi)
        for number in ("01", "02", "03", "04", "05", "06", "07", "08"):
            Table.objects.get_or_create(number=number)
        self.stdout.write(self.style.SUCCESS("Sample data ready. Credentials: admin/admin12345, cashier/cashier12345 (change them)."))
