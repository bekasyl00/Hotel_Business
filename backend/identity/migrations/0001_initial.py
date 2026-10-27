import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [("booking", "0004_guest_phone_auth")]

    operations = [
        migrations.CreateModel(
            name="GuestDevice",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=80)),
                ("auth_version", models.PositiveIntegerField()),
                ("access_hash", models.CharField(editable=False, max_length=64, unique=True)),
                ("access_expires_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField()),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="devices", to="booking.guestaccount")),
            ],
            options={"indexes": [models.Index(fields=["account", "revoked_at"], name="identity_gu_account_0d5ca1_idx")]},
        ),
        migrations.CreateModel(
            name="GuestRefreshToken",
            fields=[
                ("token_hash", models.CharField(editable=False, max_length=64, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="refresh_tokens", to="identity.guestdevice")),
            ],
        ),
    ]
