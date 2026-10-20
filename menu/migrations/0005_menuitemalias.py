from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("menu", "0004_menuitem_detail_image")]

    operations = [
        migrations.CreateModel(
            name="MenuItemAlias",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phrase", models.CharField(max_length=100)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("menu_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                               related_name="identity_aliases", to="menu.menuitem")),
            ],
            options={
                "indexes": [models.Index(fields=["is_active", "phrase"], name="menu_item_alias_active_idx")],
                "constraints": [models.UniqueConstraint(fields=["menu_item", "phrase"], name="unique_menu_item_alias")],
            },
        ),
    ]
