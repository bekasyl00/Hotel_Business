from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("commerce", "0010_operational_heartbeat")]

    operations = [
        AddIndexConcurrently(
            model_name="refundrequest",
            index=models.Index(fields=["status", "created_at"], name="refund_status_age_idx"),
        ),
        AddIndexConcurrently(
            model_name="webhookdelivery",
            index=models.Index(fields=["received_at"], name="webhook_received_at_idx"),
        ),
    ]
