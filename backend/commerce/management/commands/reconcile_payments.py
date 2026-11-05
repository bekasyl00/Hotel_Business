from django.core.management.base import BaseCommand, CommandError

from commerce.jobs import run_one, schedule_due


class Command(BaseCommand):
    help = "Process a bounded batch of durable payment jobs; schedule externally every minute."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 100:
            raise CommandError("limit must be 1..100")
        schedule_due()
        count = 0
        for _ in range(options["limit"]):
            if not run_one():
                break
            count += 1
        self.stdout.write(f"Processed {count} payment jobs")
