import math
import re
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Avg, Count, Q
from psycopg.types.range import Range
from rest_framework import serializers

from .models import Resort, Room, RoomPricePeriod, Tariff, User


def resorts_with_reviews(queryset):
    return queryset.annotate(
        approved_review_count=Count("reviews", filter=Q(reviews__status="approved")),
        approved_review_rating=Avg("reviews__rating", filter=Q(reviews__status="approved")),
    )


def validate_media_url(value):
    if not isinstance(value, str) or len(value) > 1500:
        raise serializers.ValidationError("Укажите ссылку на файл.")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError as exc:
        raise serializers.ValidationError("Недопустимая ссылка на файл.") from exc
    path = unquote(parsed.path)
    if any(ord(char) < 32 for char in value) or "\\" in value or ".." in path.split("/"):
        raise serializers.ValidationError("Недопустимая ссылка на файл.")
    relative = (
        not parsed.scheme
        and not parsed.netloc
        and path.startswith(("/assets/", "/media/", "/api/media/files/"))
        and not parsed.query
        and not parsed.fragment
    )
    remote = (
        parsed.scheme == "https" and bool(hostname) and not parsed.username and not parsed.password
    )
    if not relative and not remote:
        raise serializers.ValidationError("Нужна HTTPS-ссылка или файл из /assets/ либо /media/.")
    return value


class MediaItem(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["image", "video"])
    url = serializers.CharField(max_length=1500, validators=[validate_media_url])
    alt = serializers.CharField(max_length=200, allow_blank=True, default="")


class FeatureList(serializers.Field):
    def to_representation(self, value):
        return value

    def to_internal_value(self, value):
        if isinstance(value, str):
            value = [v.strip() for v in value.splitlines() if v.strip()]
        if (
            not isinstance(value, list)
            or len(value) > 30
            or any(not isinstance(v, str) or len(v) > 200 for v in value)
        ):
            raise serializers.ValidationError("Укажите до 30 услуг по 200 символов.")
        return value


def validate_staff_whatsapp(value):
    if not value:
        return ""
    if not re.fullmatch(r"\+?[1-9][0-9]{7,14}", value):
        raise serializers.ValidationError(
            "Укажите номер WhatsApp с кодом страны, например +77770000000."
        )
    return "+" + value.lstrip("+")


def validate_two_gis_url(value):
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname in {"2gis.kz", "2gis.com", "www.2gis.kz", "www.2gis.com"}
            and not parsed.username
            and not parsed.password
            and parsed.port in (None, 443)
        )
    except ValueError:
        valid = False
    if not valid or any(ord(char) < 32 for char in value) or "\\" in value:
        raise serializers.ValidationError("Укажите HTTPS-ссылку на 2gis.kz или 2gis.com.")
    return value


class ResortSerializer(serializers.ModelSerializer):
    bookingFeePercent = serializers.DecimalField(
        source="commission_percent", max_digits=5, decimal_places=2, read_only=True
    )
    reviewCount = serializers.SerializerMethodField()
    reviewRating = serializers.SerializerMethodField()
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    description = serializers.CharField(max_length=3000, allow_blank=True, required=False)
    descriptionAfter = serializers.CharField(
        source="description_after", max_length=5000, allow_blank=True, required=False
    )
    staffWhatsApp = serializers.CharField(
        source="staff_whatsapp",
        max_length=16,
        allow_blank=True,
        required=False,
    )
    twoGisUrl = serializers.CharField(
        source="two_gis_url",
        max_length=1000,
        allow_blank=True,
        required=False,
        validators=[validate_two_gis_url],
    )

    def validate_staffWhatsApp(self, value):
        return validate_staff_whatsapp(value)

    resortClass = serializers.ChoiceField(
        source="resort_class", choices=["standard", "comfort", "premium"], required=False
    )
    checkInTime = serializers.TimeField(
        source="check_in_time", format="%H:%M", input_formats=["%H:%M"], required=False
    )
    timeZone = serializers.CharField(source="time_zone", max_length=64, required=False)
    amenities = FeatureList(required=False)
    media = MediaItem(many=True, max_length=20, required=False)

    def review_stats(self, obj):
        if hasattr(obj, "approved_review_count"):
            return obj.approved_review_count, obj.approved_review_rating
        if not hasattr(obj, "_approved_review_stats"):
            result = obj.reviews.filter(status="approved").aggregate(
                count=Count("pk"), rating=Avg("rating")
            )
            obj._approved_review_stats = (result["count"], result["rating"])
        return obj._approved_review_stats

    def get_reviewCount(self, obj):
        return self.review_stats(obj)[0]

    def get_reviewRating(self, obj):
        rating = self.review_stats(obj)[1]
        return round(rating, 1) if rating is not None else None

    def validate_timeZone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise serializers.ValidationError(
                "Укажите часовой пояс IANA, например Asia/Almaty."
            ) from exc
        return value

    def validate(self, data):
        for key in ("lat", "lng"):
            if key in data and not math.isfinite(data[key]):
                raise serializers.ValidationError({key: "Укажите конечное число."})
        return data

    class Meta:
        model = Resort
        fields = [
            "id",
            "version",
            "name",
            "city",
            "address",
            "subtitle",
            "description",
            "descriptionAfter",
            "staffWhatsApp",
            "twoGisUrl",
            "feature",
            "lat",
            "lng",
            "rating",
            "reviewCount",
            "reviewRating",
            "bookingFeePercent",
            "status",
            "category",
            "resortClass",
            "checkInTime",
            "timeZone",
            "amenities",
            "media",
        ]
        read_only_fields = ["id", "version", "rating"]


class StaffResortSerializer(ResortSerializer):
    accountId = serializers.PrimaryKeyRelatedField(
        source="account",
        queryset=User.objects.filter(role__in=["admin", "manager"], is_active=True),
    )
    commissionPercent = serializers.DecimalField(
        source="commission_percent",
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=100,
        allow_null=True,
        required=False,
    )

    class Meta(ResortSerializer.Meta):
        fields = [*ResortSerializer.Meta.fields, "commissionPercent", "accountId"]


class PricePeriodInput(serializers.Serializer):
    label = serializers.CharField(max_length=80)
    start = serializers.DateField()
    end = serializers.DateField()
    price = serializers.IntegerField(min_value=0, max_value=10000000)

    def validate(self, data):
        if data["end"] <= data["start"]:
            raise serializers.ValidationError("Конец периода должен быть позже начала.")
        return data


class PricePeriodsField(serializers.Field):
    def to_representation(self, value):
        return [
            {
                "label": p.label,
                "start": p.stay.lower.isoformat(),
                "end": p.stay.upper.isoformat(),
                "price": p.price,
            }
            for p in value.all()
        ]

    def to_internal_value(self, value):
        serializer = PricePeriodInput(data=value, many=True, max_length=60)
        serializer.is_valid(raise_exception=True)
        periods = sorted(serializer.validated_data, key=lambda p: p["start"])
        if any(a["end"] > b["start"] for a, b in zip(periods, periods[1:], strict=False)):
            raise serializers.ValidationError("Периоды цен одного номера не должны пересекаться.")
        return periods


class PlaceStateInput(serializers.Serializer):
    id = serializers.CharField(max_length=64)
    status = serializers.ChoiceField(choices=["active", "maintenance"])


class RoomSerializer(serializers.ModelSerializer):
    places = serializers.SerializerMethodField(read_only=True)
    placeStates = PlaceStateInput(many=True, max_length=12, required=False, write_only=True)
    pricePeriods = PricePeriodsField(source="price_periods", required=False)
    resortId = serializers.PrimaryKeyRelatedField(source="resort", queryset=Resort.objects.all())
    capacity = serializers.IntegerField(min_value=1, max_value=4)
    area = serializers.IntegerField(min_value=1, max_value=1000)
    price = serializers.IntegerField(min_value=0, max_value=10000000)
    description = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    descriptionAfter = serializers.CharField(
        source="description_after", max_length=5000, allow_blank=True, required=False
    )
    amenities = FeatureList(required=False)
    media = MediaItem(many=True, max_length=20, required=False)

    def get_places(self, obj):
        places = list(obj.places.all())
        if not places and obj.pk:
            places = obj.ensure_places()
        places.sort(key=lambda item: (item.position, item.pk))
        return [
            {
                "id": p.pk,
                "position": p.position,
                "label": p.label,
                "unitLabel": f"{obj.number}{p.label}",
                "status": p.status,
            }
            for p in places
        ]

    def save_periods(self, room, periods):
        if periods is not None:
            room.price_periods.all().delete()
            RoomPricePeriod.objects.bulk_create(
                [
                    RoomPricePeriod(
                        room=room,
                        label=p["label"],
                        price=p["price"],
                        stay=Range(p["start"], p["end"], bounds="[)"),
                    )
                    for p in periods
                ]
            )
            getattr(room, "_prefetched_objects_cache", {}).pop("price_periods", None)
        return room

    def create(self, validated_data):
        validated_data.pop("placeStates", None)
        periods = validated_data.pop("price_periods", None)
        return self.save_periods(super().create(validated_data), periods)

    def update(self, instance, validated_data):
        validated_data.pop("placeStates", None)
        periods = validated_data.pop("price_periods", None)
        return self.save_periods(super().update(instance, validated_data), periods)

    class Meta:
        model = Room
        fields = [
            "id",
            "version",
            "resortId",
            "number",
            "category",
            "title",
            "area",
            "capacity",
            "beds",
            "places",
            "placeStates",
            "price",
            "pricePeriods",
            "status",
            "description",
            "descriptionAfter",
            "amenities",
            "media",
        ]
        read_only_fields = ["id", "version", "places"]
        validators = []


class TariffSerializer(serializers.ModelSerializer):
    childrenUnderTwoFree = serializers.BooleanField(
        source="children_under_two_free", required=False
    )
    resortId = serializers.PrimaryKeyRelatedField(source="resort", queryset=Resort.objects.all())
    features = FeatureList()
    supplement = serializers.IntegerField(min_value=0, max_value=10000000)
    priceKind = serializers.ChoiceField(
        source="price_kind", choices=["regular", "discount"], required=False
    )
    discountPercent = serializers.IntegerField(
        source="discount_percent", min_value=0, max_value=90, required=False
    )

    def validate(self, data):
        kind = data.get("price_kind", self.instance.price_kind if self.instance else "regular")
        percent = data.get(
            "discount_percent", self.instance.discount_percent if self.instance else 0
        )
        if kind == "regular" and percent:
            raise serializers.ValidationError(
                {"discountPercent": "У обычной цены скидка должна быть 0%."}
            )
        if kind == "discount" and percent == 0:
            raise serializers.ValidationError({"discountPercent": "Укажите скидку от 1 до 90%."})
        return data

    class Meta:
        model = Tariff
        fields = [
            "id",
            "version",
            "resortId",
            "name",
            "description",
            "supplement",
            "childrenUnderTwoFree",
            "features",
            "status",
            "priceKind",
            "discountPercent",
        ]
        read_only_fields = ["id", "version"]


class AccountInput(serializers.Serializer):
    profileVersion = serializers.IntegerField(min_value=1, required=False)
    role = serializers.ChoiceField(choices=["manager", "accountant"], required=False)
    name = serializers.CharField(max_length=100)
    login = serializers.EmailField(max_length=100)
    resortId = serializers.PrimaryKeyRelatedField(
        source="resort",
        queryset=Resort.objects.exclude(status="archived"),
        required=False,
        allow_null=True,
    )
    status = serializers.ChoiceField(choices=["active", "disabled"])
    password = serializers.CharField(min_length=12, max_length=128, required=False, write_only=True)

    def validate_login(self, value):
        value = value.strip().lower()
        existing = User.objects.filter(Q(email__iexact=value) | Q(username__iexact=value))
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError("Этот email уже используется.")
        return value


class BookingInput(serializers.Serializer):
    roomId = serializers.CharField(max_length=64)
    tariffId = serializers.CharField(max_length=64, required=False)
    start = serializers.DateField()
    end = serializers.DateField()
    guests = serializers.IntegerField(min_value=1, max_value=4)
    placeIds = serializers.ListField(
        child=serializers.CharField(max_length=64), min_length=1, max_length=4, required=False
    )
    allocationMode = serializers.CharField(max_length=32, required=False)
    childrenAges = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=13), max_length=3, default=list
    )
    childrenBirthDates = serializers.ListField(
        child=serializers.DateField(), max_length=3, required=False
    )
    childrenDatesConfirmed = serializers.BooleanField(required=False)
    guestLabel = serializers.CharField(max_length=80)
    guestPhone = serializers.RegexField(r"^\+?[0-9 ()-]{7,30}$", required=False, allow_blank=True)
    requestId = serializers.UUIDField()

    def to_internal_value(self, data):
        # Older callers may echo display prices. They are ignored; only server
        # pricing determines the charge. Identity fields are never accepted.
        ignored_prices = {"total", "nightly", "regularNightly", "discountPercent"}
        if not isinstance(data, dict) or set(data) - set(self.fields) - ignored_prices:
            raise serializers.ValidationError(
                {"non_field_errors": ["Неизвестные поля бронирования."]}
            )
        return super().to_internal_value(data)

    def validate(self, data):
        from django.utils import timezone

        births = data.pop("childrenBirthDates", None)
        # Retained for older clients, but no checkbox is required. These dates
        # are declared input, not proof of identity or verified eligibility.
        data.pop("childrenDatesConfirmed", None)
        if births is not None:
            ages = []
            for birth in births:
                checkin = data["start"]
                age = (
                    checkin.year
                    - birth.year
                    - ((checkin.month, checkin.day) < (birth.month, birth.day))
                )
                if birth > timezone.localdate() or not 0 <= age < 14:
                    raise serializers.ValidationError(
                        "Проверьте дату рождения: ребёнку должно быть меньше 14 лет на дату заезда."
                    )
                ages.append(age)
            if data["childrenAges"] and data["childrenAges"] != ages:
                raise serializers.ValidationError(
                    "Возраст не соответствует дате рождения и заезду."
                )
            data["childrenAges"] = ages

        if len(data["childrenAges"]) >= data["guests"]:
            raise serializers.ValidationError(
                {"childrenAges": "Нужен хотя бы один взрослый; дети входят в общее число гостей."}
            )
        return data


class GuestProfileInput(serializers.Serializer):
    name = serializers.CharField(max_length=80)
    phone = serializers.RegexField(r"^\+?[0-9 ()-]{7,30}$")

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - {"name", "phone"}:
            raise serializers.ValidationError(
                {"non_field_errors": ["Можно изменить только имя и телефон."]}
            )
        return super().to_internal_value(data)


def guest_profile_data(profile):
    return {
        "id": profile.pk,
        "name": profile.name,
        "phone": profile.phone,
        "avatarUrl": f"/api/media/files/{profile.avatar_id}" if profile.avatar_id else None,
        "version": profile.version,
        "createdAt": profile.created_at.isoformat(),
        "updatedAt": profile.updated_at.isoformat(),
    }


class ReviewInput(serializers.Serializer):
    bookingId = serializers.CharField(max_length=64)
    rating = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(min_length=10, max_length=3000)
    photos = serializers.ListField(
        child=serializers.CharField(max_length=1500, validators=[validate_media_url]),
        max_length=6,
        default=list,
    )


class ReviewModeration(serializers.Serializer):
    status = serializers.ChoiceField(choices=["approved", "rejected"])
    reply = serializers.CharField(max_length=2000, allow_blank=True, required=False)


def review_data(review, staff=False):
    data = {
        "id": review.id,
        "resortId": review.resort_id,
        "rating": review.rating,
        "text": review.text,
        "photos": review.photos,
        "reply": review.reply,
        "createdAt": review.created_at.isoformat(),
        "verifiedStay": True,
    }
    if staff:
        data.update(version=review.version, status=review.status, bookingId=review.booking_id)
    return data


def account_data(user):
    return {
        "id": str(user.pk),
        "name": user.name or user.username,
        "login": user.email,
        "role": "admin" if user.is_superuser else user.role,
        "resortId": user.managed_resorts.order_by("id").values_list("id", flat=True).first(),
        "resortIds": list(user.managed_resorts.order_by("id").values_list("id", flat=True)),
        "status": "active" if user.is_active else "disabled",
        "version": user.version,
        "profileVersion": user.profile_version,
        "createdAt": user.date_joined.isoformat(),
        "lastLogin": user.last_login.isoformat() if user.last_login else None,
    }


def booking_data(b, staff=False):
    from commerce.services import booking_payment_data, cancellation_terms
    from commerce.settlement import onsite_data, payment_terms

    review = getattr(b, "review", None)
    snapshot = dict(b.snapshot)
    if not staff:
        snapshot.pop("commissionTerms", None)
    if "placeIds" not in snapshot or "placeLabels" not in snapshot:
        allocs = list(b.allocations.all())
        room_number = snapshot.get("unit") or getattr(b.room, "number", "")
        snapshot.setdefault("placeIds", [a.place_id for a in allocs])
        snapshot.setdefault(
            "placeLabels",
            [
                f"{room_number}{a.place.label}"
                for a in allocs
                if getattr(a, "place", None) is not None
            ],
        )
    snapshot.setdefault(
        "placesCount",
        len(snapshot.get("placeIds") or []) or int(b.guests or 1),
    )
    return {
        "id": b.id,
        "version": b.version,
        "resortId": b.resort_id,
        "roomId": b.room_id,
        "tariffId": b.tariff_id,
        "start": b.stay.lower.isoformat(),
        "end": b.stay.upper.isoformat(),
        "guests": b.guests,
        "guestLabel": b.guest_label,
        "guestPhone": b.guest_phone,
        "status": b.status,
        "source": b.source,
        "createdAt": b.created_at.isoformat(),
        "guestProfileId": b.guest_profile_id,
        "stayStatus": "checked_out"
        if b.checked_out_at
        else ("in_house" if b.checked_in_at else "not_arrived"),
        "checkedInAt": b.checked_in_at.isoformat() if b.checked_in_at else None,
        "checkedOutAt": b.checked_out_at.isoformat() if b.checked_out_at else None,
        **snapshot,
        "paymentTerms": payment_terms(b),
        "onsitePayment": onsite_data(b),
        "holdExpiresAt": b.hold_expires_at.isoformat() if b.hold_expires_at else None,
        "cancellationPolicy": cancellation_terms(b),
        "payment": booking_payment_data(b),
        "reviewId": review.pk if review else None,
        "reviewStatus": review.status if review else None,
        **({"staffNotes": b.staff_notes} if staff else {}),
    }


def audit_data(a):
    return {
        "id": a.id,
        "at": a.at.isoformat(),
        "actor": a.actor,
        "resortId": a.resort_id,
        "entity": a.entity,
        "entityId": a.entity_id,
        "action": a.action,
        "label": a.label,
        "before": a.before,
        "after": a.after,
    }
