import uuid

from django.db import models


class GuestDevice(models.Model):
    """One revocable native-client session; credentials are never stored in plaintext."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        "booking.GuestAccount", on_delete=models.CASCADE, related_name="devices"
    )
    name = models.CharField(max_length=80)
    auth_version = models.PositiveIntegerField()
    access_hash = models.CharField(max_length=64, unique=True, editable=False)
    access_expires_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["account", "revoked_at"], name="identity_gu_account_0d5ca1_idx")
        ]


class GuestRefreshToken(models.Model):
    """Consumed hashes remain until family expiry so replay revokes that family."""

    token_hash = models.CharField(primary_key=True, max_length=64, editable=False)
    device = models.ForeignKey(GuestDevice, on_delete=models.CASCADE, related_name="refresh_tokens")
    created_at = models.DateTimeField(auto_now_add=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
