from django.core.management.base import BaseCommand, CommandError

from commerce.jobs import run_one, schedule_due
from commerce.payment_services import configuration
from commerce.providers.base import ProviderError
from commerce.providers.halyk_epay import HalykProvider


class Command(BaseCommand):
    help = "Process a bounded batch of durable sandbox jobs; schedule externally every minute."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 100:
            raise CommandError("limit must be 1..100")
        try:
            provider = HalykProvider(configuration())
        except ProviderError as exc:
            raise CommandError(exc.code) from None
        schedule_due()
        count = 0
        for _ in range(options["limit"]):
            if not run_one(provider=provider):
                break
            count += 1
        self.stdout.write(f"Processed {count} payment jobs")
