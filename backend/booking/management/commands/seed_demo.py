import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from booking.models import Resort, Room, Tariff, User


class Command(BaseCommand):
    help = "Add fictional catalogue for local development only; never resets existing records."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo is only available with DEBUG=True.")
        owner = (
            User.objects.filter(is_active=True)
            .filter(Q(role="admin") | Q(is_superuser=True))
            .first()
        )
        if owner is None:
            raise CommandError("Create a platform admin before seeding the catalogue.")
        seed = json.loads(Path(__file__).with_name("demo_catalog.json").read_text())
        for index, data in enumerate(seed["resorts"]):
            resort, created = Resort.objects.get_or_create(
                pk=data["id"],
                defaults={
                    "account": owner,
                    "name": data["name"],
                    "subtitle": data["subtitle"],
                    "description": data["description"],
                    "city": "Сарыагаш",
                    "address": "Демонстрационная курортная зона",
                    "lat": data["lat"],
                    "lng": data["lng"],
                    "feature": data["feature"],
                    "rating": data["rating"],
                    "status": "published",
                    "category": ["wellness", "family", "nature", "premium"][index % 4],
                    "resort_class": "premium" if index % 4 == 3 else "comfort",
                    "amenities": ["Wi-Fi", "Парковка", "Территория для прогулок"],
                    "media": [
                        {
                            "kind": "image",
                            "url": "/assets/resort.jpg",
                            "alt": "Иллюстративная фотография санатория",
                        }
                    ],
                },
            )
            if not created:
                continue
            for room in data["rooms"]:
                for unit in room["units"]:
                    Room.objects.create(
                        id=f"{resort.pk}-{unit}",
                        resort=resort,
                        number=unit,
                        description="Демонстрационный номер. Фотография иллюстративная; оснащение требует подтверждения санаторием.",
                        amenities=["Wi-Fi", "Собственная ванная", "Кондиционер"],
                        media=[
                            {
                                "kind": "image",
                                "url": "/assets/room.jpg",
                                "alt": "Иллюстративная фотография номера",
                            }
                        ],
                        **{
                            key: room[key]
                            for key in ["category", "title", "area", "capacity", "beds", "price"]
                        },
                    )
            for tariff in seed["tariffs"]:
                Tariff.objects.create(
                    id=f"{resort.pk}-{tariff['id']}",
                    resort=resort,
                    **{
                        key: tariff[key]
                        for key in ["name", "description", "supplement", "features"]
                    },
                )
        self.stdout.write(
            self.style.SUCCESS("Fictional catalogue ready. No accounts or passwords were created.")
        )
