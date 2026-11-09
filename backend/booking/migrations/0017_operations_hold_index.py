from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("booking", "0016_rate_limit_retention_index")]

    operations = [
        AddIndexConcurrently(
            model_name="booking",
            index=models.Index(
                fields=["hold_expires_at"],
                condition=models.Q(status="pending"),
                name="booking_pending_hold_idx",
            ),
        ),
    ]
