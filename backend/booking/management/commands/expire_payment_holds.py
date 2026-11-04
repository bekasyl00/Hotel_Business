from django.core.management.base import BaseCommand
from django.utils import timezone

from booking.holds import expire_resort_holds
from booking.models import Booking


class Command(BaseCommand):
    help = "Release expired unpaid inventory holds. Run periodically (e.g. every minute)."

    def handle(self, *args, **options):
        resort_ids = list(
            Booking.objects.filter(status="pending", hold_expires_at__lte=timezone.now())
            .values_list("resort_id", flat=True)
            .distinct()
        )
        count = sum(expire_resort_holds(pk) for pk in sorted(resort_ids))
        self.stdout.write(f"Expired holds: {count}")
