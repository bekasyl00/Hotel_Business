from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("booking", "0012_guest_phone_verification")]

    operations = [
        migrations.AddField(
            model_name="resort", name="description_after", field=models.TextField(blank=True)
        ),
        migrations.AddField(
            model_name="resort",
            name="staff_whatsapp",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.AddField(
            model_name="resort",
            name="two_gis_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="room", name="description_after", field=models.TextField(blank=True)
        ),
    ]
