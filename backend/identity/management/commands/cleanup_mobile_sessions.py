from django.core.management.base import BaseCommand
from django.utils import timezone

from identity.models import GuestDevice, StaffDevice


class Command(BaseCommand):
    help = "Delete expired mobile token families and their expired refresh-token hashes."

    def handle(self, *args, **options):
        _, counts = GuestDevice.objects.filter(expires_at__lte=timezone.now()).delete()
        _, staff = StaffDevice.objects.filter(expires_at__lte=timezone.now()).delete()
        self.stdout.write(
            f"Expired device sessions deleted: {counts.get('identity.GuestDevice', 0) + staff.get('identity.StaffDevice', 0)}"
        )
