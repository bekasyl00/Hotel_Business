from django.contrib.auth import logout
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services as svc
from .authentication import bearer_or_csrf_protect
from .errors import Problem
from .models import Audit, Booking, Resort, Review, Room, Tariff, User
from .serializers import (
    ResortSerializer,
    RoomSerializer,
    TariffSerializer,
    account_data,
    audit_data,
    booking_data,
    resorts_with_reviews,
    review_data,
)


@method_decorator(never_cache, name="dispatch")
@method_decorator(bearer_or_csrf_protect, name="dispatch")
class Endpoint(APIView):
    # Public endpoints are individually dispatched; every staff action checks scope in service layer.
    permission_classes = [AllowAny]

    def get(self, request, resource, pk=None, action=None):
        if action:
            raise Problem("Для этого действия используйте POST.", 405)
        if resource == "profile" and not pk:
            return Response(svc.current_guest_profile(request))
        if resource == "guests" and pk:
            return Response(svc.staff_guest_profile(request, pk))
        if resource == "analytics" and not pk:
            from .analytics import analytics_for_request

            return Response(analytics_for_request(request))
        if resource == "resorts" and pk:
            resort = get_object_or_404(Resort, pk=pk, status="published")
            return Response(
                {
                    "resort": ResortSerializer(resort).data,
                    "rooms": RoomSerializer(
                        resort.rooms.filter(status="active").prefetch_related("price_periods"),
                        many=True,
                    ).data,
                    "tariffs": TariffSerializer(
                        resort.tariffs.filter(status="active"), many=True
                    ).data,
                    "reviews": [
                        review_data(r)
                        for r in resort.reviews.filter(status="approved").order_by("-created_at")[
                            :100
                        ]
                    ],
                }
            )
        if resource == "rooms" and pk:
            room = get_object_or_404(
                Room.objects.select_related("resort"),
                pk=pk,
                status="active",
                resort__status="published",
            )
            return Response(
                {
                    "resort": ResortSerializer(room.resort).data,
                    "room": RoomSerializer(room).data,
                    "tariffs": TariffSerializer(
                        room.resort.tariffs.filter(status="active"), many=True
                    ).data,
                }
            )
        if pk:
            raise Problem("Не найдено.", 404)
        if resource == "categories":
            return Response(
                [
                    {"id": key, "name": title}
                    for key, title in [
                        ("wellness", "Оздоровление"),
                        ("family", "Семейный отдых"),
                        ("premium", "Премиум"),
                        ("nature", "На природе"),
                    ]
                ]
            )
        if resource == "reviews":
            resort = get_object_or_404(
                Resort, pk=request.query_params.get("resortId"), status="published"
            )
            return Response(
                [
                    review_data(r)
                    for r in resort.reviews.filter(status="approved").order_by("-created_at")[:100]
                ]
            )
        if resource == "auth/csrf":
            svc.guest_owner(request)
            return Response({"token": get_token(request)})
        if resource == "auth/session":
            return (
                Response(account_data(request.user))
                if request.user.is_authenticated
                else Response(status=204)
            )
        if resource == "catalog":
            resorts = Resort.objects.filter(status="published")
            return Response(
                {
                    "resorts": ResortSerializer(resorts_with_reviews(resorts), many=True).data,
                    "rooms": RoomSerializer(
                        Room.objects.filter(resort__in=resorts, status="active").prefetch_related(
                            "price_periods"
                        ),
                        many=True,
                    ).data,
                    "tariffs": TariffSerializer(
                        Tariff.objects.filter(resort__in=resorts, status="active"), many=True
                    ).data,
                }
            )
        if resource == "availability":
            start = serializers.DateField().run_validation(request.query_params.get("start"))
            end = serializers.DateField().run_validation(request.query_params.get("end"))
            guests = serializers.IntegerField(min_value=1, max_value=4).run_validation(
                request.query_params.get("guests", 1)
            )
            stay = svc.validated_dates(start, end)
            occupied = Booking.objects.filter(status__in=svc.ACTIVE, stay__overlap=stay).values(
                "room_id"
            )
            ids = (
                Room.objects.filter(
                    resort__status="published", status="active", capacity__gte=guests
                )
                .exclude(pk__in=occupied)
                .values_list("id", flat=True)
            )
            return Response({"roomIds": list(ids)})
        if resource == "my-bookings":
            return Response(
                [
                    booking_data(b)
                    for b in Booking.objects.filter(
                        owner=svc.guest_owner(request), source="website"
                    )
                    .select_related("review")
                    .prefetch_related("demo_payments")
                    .order_by("-created_at")
                ]
            )
        if resource == "workspace":
            svc.require_staff(request.user)
            resorts = (
                Resort.objects.all()
                if svc.admin(request.user)
                else Resort.objects.filter(pk=request.user.resort_id)
            )
            audit = (
                Audit.objects.all()
                if svc.admin(request.user)
                else Audit.objects.filter(resort__in=resorts)
            )
            return Response(
                {
                    "resorts": ResortSerializer(resorts_with_reviews(resorts), many=True).data,
                    "rooms": RoomSerializer(
                        Room.objects.filter(resort__in=resorts).prefetch_related("price_periods"),
                        many=True,
                    ).data,
                    "tariffs": TariffSerializer(
                        Tariff.objects.filter(resort__in=resorts), many=True
                    ).data,
                    "bookings": [
                        booking_data(b)
                        for b in Booking.objects.filter(resort__in=resorts)
                        .select_related("review")
                        .prefetch_related("demo_payments")
                        .order_by("-created_at")
                    ],
                    "accounts": [
                        account_data(u)
                        for u in User.objects.filter(role="manager", is_superuser=False)
                    ]
                    if svc.admin(request.user)
                    else [],
                    "audit": [audit_data(a) for a in audit.order_by("-at")[:500]],
                    "reviews": [
                        review_data(r, staff=True)
                        for r in Review.objects.filter(resort__in=resorts).order_by("-created_at")[
                            :500
                        ]
                    ],
                }
            )
        raise Problem("Не найдено.", 404)

    def post(self, request, resource, pk=None, action=None):
        if resource == "bookings" and pk and action in ["check-in", "check-out"]:
            return Response(booking_data(svc.change_stay(request, pk, action)))
        if pk:
            raise Problem("Не найдено.", 404)
        if resource == "auth/login":
            return Response(svc.login_account(request))
        if resource == "auth/logout":
            logout(request)
            return Response(status=204)
        if resource in ["my-bookings", "bookings"]:
            return Response(
                booking_data(svc.create_booking(request, resource == "bookings")), status=201
            )
        if resource == "accounts":
            return Response(svc.save_account(request), status=201)
        if resource == "reviews":
            return Response(svc.create_review(request), status=201)
        if resource in svc.SERIALIZERS:
            return Response(svc.save_catalog(request, resource), status=201)
        raise Problem("Не найдено.", 404)

    def patch(self, request, resource, pk=None, action=None):
        if action:
            raise Problem("Для этого действия используйте POST.", 405)
        if resource == "profile" and not pk:
            return Response(svc.update_guest_profile(request))
        if not pk:
            raise Problem("Не найдено.", 404)
        if resource in ["my-bookings", "bookings"]:
            return Response(
                booking_data(svc.transition_booking(request, pk, resource == "bookings"))
            )
        if resource == "accounts":
            return Response(svc.save_account(request, pk))
        if resource == "reviews":
            return Response(svc.moderate_review(request, pk))
        if resource in svc.SERIALIZERS:
            return Response(svc.save_catalog(request, resource, pk))
        raise Problem("Не найдено.", 404)

    def delete(self, request, resource, pk=None, action=None):
        if action:
            raise Problem("Для этого действия используйте POST.", 405)
        if not pk or resource not in svc.SERIALIZERS:
            raise Problem("Не найдено.", 404)
        result = svc.delete_catalog(request, resource, pk)
        return Response(result, status=200 if result else 204)
