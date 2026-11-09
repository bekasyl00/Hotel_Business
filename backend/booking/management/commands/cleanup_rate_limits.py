from django.core.management.base import BaseCommand, CommandError

from booking.rate_limits import prune_limits


class Command(BaseCommand):
    help = "Inspect dormant rate-limit/scope rows; --delete prunes a bounded batch."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--limit", type=int, default=1000)
        parser.add_argument("--delete", action="store_true")

    def handle(self, *args, **options):
        try:
            count = prune_limits(
                days=options["days"], limit=options["limit"], delete=options["delete"]
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from None
        action = "Deleted" if options["delete"] else "Eligible (dry run)"
        self.stdout.write(f"{action}: {count} dormant rate-limit rows.")
