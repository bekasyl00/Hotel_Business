from django.core.management.base import BaseCommand, CommandError

from booking.push import send_due_pushes


class Command(BaseCommand):
    help = "Deliver a bounded batch of pending StaffPushDelivery records via FCM/APNs."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= 200:
            raise CommandError("limit must be 1..200")
        count = send_due_pushes(limit=limit)
        self.stdout.write(f"Processed {count} staff push deliveries")
