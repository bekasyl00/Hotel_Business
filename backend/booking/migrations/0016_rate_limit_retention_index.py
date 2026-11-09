from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [("booking", "0015_staff_profile")]

    operations = [
        AddIndexConcurrently(
            model_name="loginattempt",
            index=models.Index(fields=["since"], name="booking_rate_since_idx"),
        ),
    ]
