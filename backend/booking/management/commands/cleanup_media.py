from datetime import timedelta

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from booking.media_access import asset_is_referenced
from booking.models import GuestProfile, MediaAsset, Resort


class Command(BaseCommand):
    help = "List unreferenced uploads older than 24h. --delete removes files and their metadata."

    def add_arguments(self, parser):
        parser.add_argument("--delete", action="store_true")
        parser.add_argument("--hours", type=int, default=24)
        parser.add_argument("--limit", type=int, default=500)

    def handle(self, *args, **options):
        if options["hours"] < 24 or not 1 <= options["limit"] <= 5000:
            raise CommandError("Use --hours >= 24 and --limit between 1 and 5000.")
        candidates = (
            MediaAsset.objects.filter(
                created_at__lt=timezone.now() - timedelta(hours=options["hours"])
            )
            .order_by("created_at")
            .values_list("pk", flat=True)
        )
        count, examined = 0, 0
        for pk in candidates.iterator(chunk_size=200):
            examined += 1
            with transaction.atomic():
                asset = MediaAsset.objects.filter(pk=pk).first()
                if not asset:
                    continue
                # Match catalogue/profile mutation locks to avoid deleting a file while it is attached.
                if asset.resort_id:
                    Resort.objects.select_for_update().get(pk=asset.resort_id)
                else:
                    GuestProfile.objects.select_for_update().get(pk=asset.profile_id)
                if asset_is_referenced(asset):
                    continue
                if options["delete"]:
                    default_storage.delete(asset.storage_key)
                    asset.delete()
                count += 1
            if count >= options["limit"]:
                break
        verb = "Deleted" if options["delete"] else "Would delete"
        self.stdout.write(f"{verb} {count} unreferenced uploads; examined {examined} records.")
