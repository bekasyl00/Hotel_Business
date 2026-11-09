import time

from django.core.management.base import BaseCommand, CommandError

from commerce.jobs import run_one, schedule_due
from commerce.operations import finish_heartbeat, start_heartbeat


class Command(BaseCommand):
    help = "Process a bounded batch of durable payment jobs; schedule externally every minute."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 100:
            raise CommandError("limit must be 1..100")
        started = time.monotonic()
        token = start_heartbeat("payment_worker")
        count = 0
        try:
            schedule_due()
            for _ in range(options["limit"]):
                if not run_one():
                    break
                count += 1
        except Exception:
            finish_heartbeat(
                "payment_worker",
                token,
                succeeded=False,
                duration=time.monotonic() - started,
                processed=count,
            )
            raise
        finish_heartbeat(
            "payment_worker",
            token,
            succeeded=True,
            duration=time.monotonic() - started,
            processed=count,
        )
        self.stdout.write(f"Processed {count} payment jobs")
