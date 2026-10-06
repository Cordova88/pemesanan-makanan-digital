from decimal import Decimal
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from menu.models import AddOn, Category, MenuItem, MenuTag, VariantGroup, VariantOption
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
        tags={name:MenuTag.objects.get_or_create(name=name, defaults={"display_name":name.title()})[0] for name in ("spicy","savory","sweet","filling","light","crispy","cheesy","chicken","rice","noodle","snack","drink","cold")}
        def menu(name, category, price, tag_names, **defaults):
            item,_=MenuItem.objects.get_or_create(name=name,category=category,defaults={"price":Decimal(price),**defaults}); item.tags.set([tags[tag] for tag in tag_names]); return item
        nasi=menu("Nasi Goreng",foods,"15000.00",("rice","savory","filling"),description="Nasi goreng spesial")
        menu("Ayam Geprek",foods,"15000.00",("chicken","rice","spicy","crispy","filling"))
        menu("Mie Goreng",foods,"14000.00",("noodle","savory","filling"))
        menu("Mie Pedas",foods,"15000.00",("noodle","spicy","filling"))
        menu("Tahu Crispy",foods,"10000.00",("snack","crispy","light"))
        menu("Es Teh",drinks,"5000.00",("drink","sweet","cold"))
        menu("Es Jeruk",drinks,"8000.00",("drink","sweet","cold"))
        menu("Ayam Geprek Mozzarella",foods,"20000.00",("chicken","rice","spicy","cheesy","filling"))
        group,_=VariantGroup.objects.get_or_create(menu_item=nasi,name="Ukuran",defaults={"is_required":True})
        VariantOption.objects.get_or_create(group=group,name="Regular",defaults={"price_adjustment":0})
        VariantOption.objects.get_or_create(group=group,name="Large",defaults={"price_adjustment":Decimal("4000.00")})
        for name,price in (("Extra Sambal","3000.00"),("Extra Cheese","5000.00")):
            addon,_=AddOn.objects.get_or_create(name=name,defaults={"price":Decimal(price)}); addon.menu_items.add(nasi)
        for number in ("01", "02", "03", "04", "05", "06", "07", "08"):
            Table.objects.get_or_create(number=number)
        self.stdout.write(self.style.SUCCESS("Sample data ready. Credentials: admin/admin12345, cashier/cashier12345 (change them)."))
