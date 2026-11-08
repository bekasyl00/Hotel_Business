from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("booking", "0014_children_under_two_free")]

    operations = [
        migrations.AddField(
            model_name="user", name="job_title", field=models.CharField(blank=True, max_length=100)
        ),
        migrations.AddField(
            model_name="user",
            name="contact_phone",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.AddField(
            model_name="user", name="profile_version", field=models.PositiveIntegerField(default=1)
        ),
    ]
