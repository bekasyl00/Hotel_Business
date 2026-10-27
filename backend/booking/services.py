import hashlib
import json
import secrets
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import authenticate, login
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.db.models import Avg
from django.shortcuts import get_object_or_404
from django.utils import timezone
from psycopg.types.range import Range

from commerce.services import apply_cancellation, freeze_cancellation_terms

from .errors import Problem
from .models import (
    Audit,
    Booking,
    GuestAccount,
    GuestProfile,
    LoginAttempt,
    Resort,
    Review,
    Room,
    Tariff,
    User,
)
from .serializers import (
    AccountInput,
    BookingInput,
    GuestProfileInput,
    ResortSerializer,
    ReviewInput,
    ReviewModeration,
    RoomSerializer,
    TariffSerializer,
    account_data,
    booking_data,
    guest_profile_data,
    review_data,
)

ACTIVE = ["pending", "confirmed"]
SERIALIZERS = {"resorts": ResortSerializer, "rooms": RoomSerializer, "tariffs": TariffSerializer}
MODELS = {
    "resorts": Resort,
    "rooms": Room,
    "tariffs": Tariff,
    "accounts": User,
    "bookings": Booking,
}


def admin(user):
    return user.is_authenticated and (user.is_superuser or user.role == "admin")


def require_staff(user, resort_id=None):
    if not user.is_authenticated:
        raise Problem("Войдите в кабинет сотрудника.", 401)
    if not admin(user) and (
        not user.resort_id or (resort_id and str(user.resort_id) != str(resort_id))
    ):
        raise Problem("У вас нет доступа к этому санаторию.", 403)


def require_admin(user):
    require_staff(user)
    if not admin(user):
        raise Problem("Доступно только администратору.", 403)


def guest_owner(request):
    from .guest_auth import current_account

    account = current_account(request)
    if account:
        return account.profile.owner
    if "guest_owner" not in request.session:
        request.session["guest_owner"] = secrets.token_hex(32)
    return request.session["guest_owner"]


def version_check(item, data):
    if type(data.get("version")) is not int or data["version"] != item.version:
        raise Problem("Запись уже изменена. Обновите данные и повторите.", 409)


def log_change(user, entity, item, action, before, after, resort_id=None, website=False):
    def redact(data):
        if data is None:
            return None
        return {k: v for k, v in data.items() if k not in ["guestPhone", "password"]}

    Audit.objects.create(
        actor="Гость сайта" if website else (user.name or user.username),
        resort_id=resort_id,
        entity=entity,
        entity_id=str(item.pk),
        action=action,
        label=(after or before or {}).get("name", (after or before or {}).get("roomName", entity)),
        before=redact(before),
        after=redact(after),
    )


def authenticate_staff_credentials(request):
    email = str(request.data.get("email", "")).strip().lower()[:254]
    password = request.data.get("password", "")
    if not isinstance(password, str) or len(password) > 128:
        raise Problem("Неверный email или пароль.", 401)
    # Database-backed limit is shared across workers; never trust arbitrary forwarded IP headers.
    keys = [
        hashlib.sha256(("email:" + email).encode()).hexdigest(),
        hashlib.sha256(("ip:" + request.META.get("REMOTE_ADDR", "")).encode()).hexdigest(),
    ]
    now = timezone.now()
    with transaction.atomic():
        for key in sorted(keys):
            LoginAttempt.objects.get_or_create(key=key, defaults={"since": now})
            attempt = LoginAttempt.objects.select_for_update().get(pk=key)
            if attempt.since < now - timedelta(minutes=15):
                attempt.count, attempt.since = 0, now
            if attempt.count >= 30:
                raise Problem("Слишком много попыток. Повторите через 15 минут.", 429)
            attempt.count += 1
            attempt.save()
    user = authenticate(request, username=email, password=password)
    if not user:
        raise Problem("Неверный email или пароль.", 401)
    require_staff(user)
    return user


def login_account(request):
    user = authenticate_staff_credentials(request)
    login(request, user)
    return account_data(user)


def validated_dates(start, end):
    if start < timezone.localdate() or end <= start or (end - start).days > 30:
        raise Problem("Выберите будущий заезд и выезд через 1–30 ночей.")
    return Range(start, end, bounds="[)")


@transaction.atomic
def create_booking(request, staff=False):
    inp = BookingInput(data=request.data)
    inp.is_valid(raise_exception=True)
    data = inp.validated_data
    owner = f"user:{request.user.pk}" if staff else guest_owner(request)
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    room = get_object_or_404(Room, pk=data["roomId"])
    resort = Resort.objects.select_for_update().get(pk=room.resort_id)
    room.refresh_from_db()
    if staff:
        require_staff(request.user, resort.pk)
    previous = Booking.objects.filter(request_key=data["requestId"]).first()
    if previous:
        if previous.owner != owner or previous.request_hash != fingerprint:
            raise Problem("Ключ запроса уже использован для другой брони.", 409)
        return previous
    tariff = get_object_or_404(Tariff, pk=data["tariffId"], resort=resort)
    if resort.status != "published" or room.status != "active" or tariff.status != "active":
        raise Problem("Санаторий, номер или тариф недоступен.", 409)
    if data["guests"] > room.capacity:
        raise Problem("Число гостей превышает вместимость номера.")
    if not staff and not data.get("guestPhone"):
        raise Problem("Укажите телефон для связи с управляющим.")
    stay = validated_dates(data["start"], data["end"])
    if Booking.objects.filter(room=room, status__in=ACTIVE, stay__overlap=stay).exists():
        raise Problem("Номер уже занят на выбранные даты. Выберите другой.", 409)
    nights = (data["end"] - data["start"]).days
    regular_nightly = room.price + tariff.supplement * data["guests"]
    discount_percent = tariff.discount_percent if tariff.price_kind == "discount" else 0
    nightly = (regular_nightly * (100 - discount_percent) + 50) // 100
    profile = (
        upsert_guest_profile(owner, data["guestLabel"], data["guestPhone"]) if not staff else None
    )
    booking = Booking.objects.create(
        resort=resort,
        room=room,
        tariff=tariff,
        stay=stay,
        guests=data["guests"],
        guest_label=data["guestLabel"],
        guest_phone=data.get("guestPhone", ""),
        owner=owner,
        guest_profile=profile,
        source="staff" if staff else "website",
        request_key=data["requestId"],
        request_hash=fingerprint,
        snapshot={
            "resortName": resort.name,
            "roomName": room.title,
            "unit": room.number,
            "tariffName": tariff.name,
            "regularNightly": regular_nightly,
            "priceKind": tariff.price_kind,
            "discountPercent": discount_percent,
            "nightly": nightly,
            "nights": nights,
            "total": nightly * nights,
            "cancellationPolicy": freeze_cancellation_terms(resort, data["start"]),
        },
    )
    log_change(
        request.user,
        "bookings",
        booking,
        "create",
        None,
        booking_data(booking),
        resort.pk,
        not staff,
    )
    return booking


@transaction.atomic
def transition_booking(request, pk, staff=False):
    item = get_object_or_404(Booking, pk=pk)
    Resort.objects.select_for_update().get(pk=item.resort_id)
    item.refresh_from_db()
    if staff:
        require_staff(request.user, item.resort_id)
    elif item.source != "website" or item.owner != guest_owner(request):
        raise Problem("Бронирование не найдено.", 404)
    version_check(item, request.data)
    target = request.data.get("status")
    allowed = {"pending": ["confirmed", "rejected", "cancelled"], "confirmed": ["cancelled"]}
    if target not in allowed.get(item.status, []) or (not staff and target != "cancelled"):
        raise Problem("Этот переход статуса недоступен.", 409)
    if item.checked_in_at:
        raise Problem("Гость уже заселён. Используйте выезд вместо отмены бронирования.", 409)
    if item.stay.upper <= timezone.localdate():
        raise Problem("Завершённое проживание нельзя изменить.", 409)
    before = booking_data(item)
    if target == "cancelled":
        item.snapshot = {
            **item.snapshot,
            "cancellation": apply_cancellation(item, request.user, staff=staff),
        }
    item.status = target
    item.version += 1
    item.save(update_fields=["status", "version", "snapshot"])
    log_change(
        request.user,
        "bookings",
        item,
        target,
        before,
        booking_data(item),
        item.resort_id,
        not staff,
    )
    return item


@transaction.atomic
def save_catalog(request, kind, pk=None):
    from .media_access import validate_asset_references

    require_staff(request.user)
    model, serializer_cls = MODELS[kind], SERIALIZERS[kind]
    item = get_object_or_404(model, pk=pk) if pk else None
    resort_id = (
        item.pk
        if kind == "resorts" and item
        else (item.resort_id if item else request.data.get("resortId"))
    )
    if kind == "resorts" and not item:
        require_admin(request.user)
    if resort_id:
        require_staff(request.user, resort_id)
        resort = get_object_or_404(Resort.objects.select_for_update(), pk=resort_id)
        if resort.status == "archived":
            raise Problem("Санаторий в архиве.", 409)
    if item:
        item.refresh_from_db()
        version_check(item, request.data)
    inp = serializer_cls(item, data=request.data, partial=bool(item))
    inp.is_valid(raise_exception=True)
    data = inp.validated_data
    if "media" in data:
        validate_asset_references(data["media"], purpose="catalog", resort_id=resort_id)
    if kind != "resorts":
        if item and data.get("resort", item.resort).pk != item.resort_id:
            raise Problem("Нельзя переносить запись в другой санаторий.")
        require_staff(request.user, (data.get("resort") or item.resort).pk)
    if kind == "resorts":
        target = data.get("status", item.status if item else "draft")
        if target == "archived":
            raise Problem("Для архивирования используйте отдельное действие.")
        if target == "published" and (
            not item
            or not item.rooms.filter(status="active").exists()
            or not item.tariffs.filter(status="active").exists()
        ):
            raise Problem("Для публикации добавьте активный номер и тариф.")
    if kind == "rooms" and item:
        future = Booking.objects.filter(
            room=item, status__in=ACTIVE, stay__endswith__gt=timezone.localdate()
        )
        if data.get("status") == "maintenance" and future.exists():
            raise Problem("Есть активные брони. Сначала отмените их.", 409)
        if future.filter(guests__gt=data.get("capacity", item.capacity)).exists():
            raise Problem("Вместимость меньше числа гостей в активной брони.", 409)
    before = dict(serializer_cls(item).data) if item else None
    result = inp.save(version=item.version + 1 if item else 1)
    after = dict(serializer_cls(result).data)
    log_change(
        request.user,
        kind,
        result,
        "update" if item else "create",
        before,
        after,
        result.pk if kind == "resorts" else result.resort_id,
    )
    return after


@transaction.atomic
def delete_catalog(request, kind, pk):
    item = get_object_or_404(MODELS[kind], pk=pk)
    resort_id = item.pk if kind == "resorts" else item.resort_id
    require_staff(request.user, resort_id)
    Resort.objects.select_for_update().get(pk=resort_id)
    item.refresh_from_db()
    version_check(item, request.data)
    before = dict(SERIALIZERS[kind](item).data)
    if kind == "resorts":
        require_admin(request.user)
        if Booking.objects.filter(
            resort=item, status__in=ACTIVE, stay__endswith__gt=timezone.localdate()
        ).exists():
            raise Problem("Есть активные брони. Сначала отмените их.", 409)
        item.status = "archived"
        item.version += 1
        item.save(update_fields=["status", "version"])
        after = dict(SERIALIZERS[kind](item).data)
        log_change(request.user, kind, item, "archive", before, after, resort_id)
        return after
    log_change(request.user, kind, item, "delete", before, None, resort_id)
    item.delete()
    return None


@transaction.atomic
def save_account(request, pk=None):
    require_admin(request.user)
    if pk and (not str(pk).isdigit() or len(str(pk)) > 18):
        raise Problem("Аккаунт не найден.", 404)
    item = (
        get_object_or_404(
            User.objects.select_for_update(), pk=pk, role="manager", is_superuser=False
        )
        if pk
        else None
    )
    if item:
        version_check(item, request.data)
    inp = AccountInput(instance=item, data=request.data)
    inp.is_valid(raise_exception=True)
    data = inp.validated_data
    password = data.get("password")
    if not item and not password:
        raise Problem("Задайте начальный пароль управляющего (от 12 символов).")
    before = account_data(item) if item else None
    item = item or User()
    item.name, item.email, item.username = data["name"], data["login"], data["login"]
    item.resort, item.is_active = data["resort"], data["status"] == "active"
    if password:
        validate_password(password, item)
        item.set_password(password)
    item.version = item.version + 1 if pk else 1
    item.save()
    after = account_data(item)
    log_change(
        request.user, "accounts", item, "update" if pk else "create", before, after, item.resort_id
    )
    return after


def review_booking(request, booking_id):
    if request.user.is_authenticated:
        raise Problem("Отзывы о проживании доступны гостям, а не сотрудникам.", 403)
    booking = get_object_or_404(
        Booking.objects.select_related("resort"),
        pk=booking_id,
        source="website",
        owner=guest_owner(request),
    )
    today = timezone.now().astimezone(ZoneInfo(booking.resort.time_zone)).date()
    if booking.status != "confirmed" or booking.stay.upper > today:
        raise Problem("Отзыв доступен после завершения подтверждённого проживания.", 409)
    return booking


@transaction.atomic
def create_review(request):
    from .media_access import validate_asset_references

    inp = ReviewInput(data=request.data)
    inp.is_valid(raise_exception=True)
    data = inp.validated_data
    booking = review_booking(request, data["bookingId"])
    Resort.objects.select_for_update().get(pk=booking.resort_id)
    validate_asset_references(
        data["photos"], purpose="review", resort_id=booking.resort_id, booking_id=booking.pk
    )
    if Review.objects.filter(booking=booking).exists():
        raise Problem("Отзыв об этом проживании уже отправлен.", 409)
    review = Review.objects.create(
        resort=booking.resort,
        booking=booking,
        rating=data["rating"],
        text=data["text"],
        photos=data["photos"],
    )
    log_change(
        request.user,
        "reviews",
        review,
        "create",
        None,
        review_data(review, staff=True),
        booking.resort_id,
        website=True,
    )
    return review_data(review, staff=True)


@transaction.atomic
def moderate_review(request, pk):
    review = get_object_or_404(Review, pk=pk)
    require_staff(request.user, review.resort_id)
    Resort.objects.select_for_update().get(pk=review.resort_id)
    review.refresh_from_db()
    version_check(review, request.data)
    inp = ReviewModeration(data=request.data)
    inp.is_valid(raise_exception=True)
    before = review_data(review, staff=True)
    review.status = inp.validated_data["status"]
    review.reply = inp.validated_data.get("reply", review.reply)
    review.version += 1
    review.save(update_fields=["status", "reply", "version"])
    average = Review.objects.filter(resort_id=review.resort_id, status="approved").aggregate(
        value=Avg("rating")
    )["value"]
    Resort.objects.filter(pk=review.resort_id).update(rating=round(average or 0, 1))
    after = review_data(review, staff=True)
    log_change(request.user, "reviews", review, review.status, before, after, review.resort_id)
    return after


@transaction.atomic
def upsert_guest_profile(owner, name, phone):
    profile, created = GuestProfile.objects.get_or_create(
        owner=owner, defaults={"name": name, "phone": phone}
    )
    if not created:
        profile = GuestProfile.objects.select_for_update().get(pk=profile.pk)
        verified_phone = (
            GuestAccount.objects.filter(profile=profile).values_list("phone", flat=True).first()
        )
        if verified_phone:
            phone = verified_phone
        if profile.name != name or profile.phone != phone:
            profile.name, profile.phone = name, phone
            profile.version += 1
            profile.save(update_fields=["name", "phone", "version", "updated_at"])
    return profile


def profile_bookings(queryset):
    return [
        booking_data(b)
        for b in queryset.select_related("review")
        .prefetch_related("demo_payments")
        .order_by("-created_at")
    ]


def current_guest_profile(request):
    owner = guest_owner(request)
    profile, _ = GuestProfile.objects.get_or_create(owner=owner, defaults={"name": "", "phone": ""})
    return {
        "profile": guest_profile_data(profile),
        "bookings": profile_bookings(Booking.objects.filter(owner=owner, source="website")),
    }


@transaction.atomic
def update_guest_profile(request):
    from .guest_auth import current_account, normalize_phone

    inp = GuestProfileInput(data=request.data)
    inp.is_valid(raise_exception=True)
    owner = guest_owner(request)
    account = current_account(request)
    if account and normalize_phone(inp.validated_data["phone"]) != account.phone:
        raise Problem(
            "Изменение телефона требует отдельного подтверждения новым кодом.",
            422,
            "phone_change_requires_verification",
        )
    previous = GuestProfile.objects.select_for_update().filter(owner=owner).first()
    before = {"id": previous.pk, "version": previous.version} if previous else None
    profile = upsert_guest_profile(owner, inp.validated_data["name"], inp.validated_data["phone"])
    log_change(
        request.user,
        "guestProfiles",
        profile,
        "update" if previous else "create",
        before,
        {"id": profile.pk, "version": profile.version},
        website=True,
    )
    return current_guest_profile(request)


def staff_guest_profile(request, pk):
    require_staff(request.user)
    bookings = Booking.objects.filter(guest_profile_id=pk, source="website")
    if not admin(request.user):
        bookings = bookings.filter(resort_id=request.user.resort_id)
    if not bookings.exists():
        raise Problem("Профиль гостя не найден.", 404)
    profile = get_object_or_404(GuestProfile, pk=pk)
    return {"profile": guest_profile_data(profile), "bookings": profile_bookings(bookings)}


@transaction.atomic
def change_stay(request, pk, action):
    require_staff(request.user)
    item = get_object_or_404(Booking, pk=pk)
    require_staff(request.user, item.resort_id)
    resort = Resort.objects.select_for_update().get(pk=item.resort_id)
    item.refresh_from_db()
    version_check(item, request.data)
    if item.status != "confirmed":
        raise Problem("Заселение и выезд доступны только для подтверждённой брони.", 409)
    if not item.demo_payments.filter(outcome="success", status="paid").exists():
        raise Problem("Сначала требуется успешная демонстрационная оплата.", 409)
    now = timezone.now()
    if action == "check-in":
        today = now.astimezone(ZoneInfo(resort.time_zone)).date()
        if item.checked_in_at or item.checked_out_at:
            raise Problem("Заселение уже зарегистрировано.", 409)
        if not item.stay.lower <= today < item.stay.upper:
            raise Problem("Заселение доступно только в даты проживания.", 409)
    elif action == "check-out":
        if not item.checked_in_at or item.checked_out_at:
            raise Problem("Для выезда гость должен быть заселён и ещё не выехать.", 409)
    else:
        raise Problem("Действие не найдено.", 404)
    before = booking_data(item)
    if action == "check-in":
        item.checked_in_at = now
    else:
        item.checked_out_at = now
    item.version += 1
    item.save(update_fields=["checked_in_at", "checked_out_at", "version"])
    after = booking_data(item)
    log_change(request.user, "bookings", item, action, before, after, item.resort_id)
    return item
