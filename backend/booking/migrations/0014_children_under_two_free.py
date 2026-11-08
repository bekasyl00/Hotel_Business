from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("booking", "0013_catalog_profile_content")]

    operations = [
        migrations.AlterField(
            model_name="tariff",
            name="children_under_three_free",
            field=models.BooleanField(default=False, db_column="children_under_three_free"),
        ),
        migrations.RenameField(
            model_name="tariff",
            old_name="children_under_three_free",
            new_name="children_under_two_free",
        ),
    ]
