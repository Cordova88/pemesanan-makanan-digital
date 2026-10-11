from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0002_menutag_menuitem_tags"),
    ]

    operations = [
        migrations.CreateModel(
            name="MenuTagAlias",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("phrase", models.CharField(max_length=100)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "tag",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="aliases",
                        to="menu.menutag",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="menutagalias",
            constraint=models.UniqueConstraint(
                fields=("tag", "phrase"),
                name="unique_menu_tag_alias",
            ),
        ),
        migrations.AddIndex(
            model_name="menutagalias",
            index=models.Index(
                fields=("is_active", "phrase"),
                name="menu_menuta_is_acti_77d923_idx",
            ),
        ),
    ]
