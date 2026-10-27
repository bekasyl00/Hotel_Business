import math
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


class ResortSerializer(serializers.ModelSerializer):
    reviewCount = serializers.SerializerMethodField()
    reviewRating = serializers.SerializerMethodField()
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    description = serializers.CharField(max_length=3000, allow_blank=True, required=False)
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
            "feature",
            "lat",
            "lng",
            "rating",
            "reviewCount",
            "reviewRating",
            "status",
            "category",
            "resortClass",
            "checkInTime",
            "timeZone",
            "amenities",
            "media",
        ]
        read_only_fields = ["id", "version", "rating"]


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


class RoomSerializer(serializers.ModelSerializer):
    pricePeriods = PricePeriodsField(source="price_periods", required=False)
    resortId = serializers.PrimaryKeyRelatedField(source="resort", queryset=Resort.objects.all())
    capacity = serializers.IntegerField(min_value=1, max_value=4)
    area = serializers.IntegerField(min_value=1, max_value=1000)
    price = serializers.IntegerField(min_value=0, max_value=10000000)
    description = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    amenities = FeatureList(required=False)
    media = MediaItem(many=True, max_length=20, required=False)

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
        periods = validated_data.pop("price_periods", None)
        return self.save_periods(super().create(validated_data), periods)

    def update(self, instance, validated_data):
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
            "price",
            "pricePeriods",
            "status",
            "description",
            "amenities",
            "media",
        ]
        read_only_fields = ["id", "version"]
        validators = []


class TariffSerializer(serializers.ModelSerializer):
    childrenUnderThreeFree = serializers.BooleanField(
        source="children_under_three_free", required=False
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
            "childrenUnderThreeFree",
            "features",
            "status",
            "priceKind",
            "discountPercent",
        ]
        read_only_fields = ["id", "version"]


class AccountInput(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    login = serializers.EmailField(max_length=100)
    resortId = serializers.PrimaryKeyRelatedField(
        source="resort", queryset=Resort.objects.exclude(status="archived")
    )
    status = serializers.ChoiceField(choices=["active", "disabled"])
    password = serializers.CharField(min_length=12, max_length=128, required=False, write_only=True)

    def validate_login(self, value):
        existing = User.objects.filter(email__iexact=value)
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError("Этот email уже используется.")
        return value.lower()


class BookingInput(serializers.Serializer):
    roomId = serializers.CharField(max_length=64)
    tariffId = serializers.CharField(max_length=64)
    start = serializers.DateField()
    end = serializers.DateField()
    guests = serializers.IntegerField(min_value=1, max_value=4)
    childrenAges = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=17), max_length=3, default=list
    )
    guestLabel = serializers.CharField(max_length=80)
    guestPhone = serializers.RegexField(r"^\+?[0-9 ()-]{7,30}$", required=False, allow_blank=True)
    requestId = serializers.UUIDField()

    def validate(self, data):
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
        "resortId": user.resort_id,
        "status": "active" if user.is_active else "disabled",
        "version": user.version,
    }


def booking_data(b):
    from commerce.services import booking_payment_data, cancellation_terms

    review = getattr(b, "review", None)
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
        **b.snapshot,
        "cancellationPolicy": cancellation_terms(b),
        "payment": booking_payment_data(b),
        "reviewId": review.pk if review else None,
        "reviewStatus": review.status if review else None,
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
