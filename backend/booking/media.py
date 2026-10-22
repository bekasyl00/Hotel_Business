import io
import uuid
import warnings

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import (
    FileResponse,
    Http404,
    HttpResponse,
    HttpResponseRedirect,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import bearer_or_csrf_protect
from .errors import Problem
from .media_access import can_read_asset, enforce_upload_quota
from .models import Audit, GuestProfile, MediaAsset, Resort
from .serializers import guest_profile_data
from .services import require_staff, review_booking

IMAGE_LIMIT = 8 * 1024 * 1024
VIDEO_LIMIT = 40 * 1024 * 1024


def safe_image(upload):
    if upload.size > IMAGE_LIMIT:
        raise Problem("Фотография должна быть не больше 8 МБ.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(upload)
            if (
                image.format not in {"JPEG", "PNG", "WEBP"}
                or image.width * image.height > 20_000_000
            ):
                raise Problem("Нужна фотография JPEG, PNG или WebP до 20 мегапикселей.")
            image.load()
            image = ImageOps.exif_transpose(image)
            image.thumbnail((2400, 2400))
            image = image.convert("RGB")
            content = io.BytesIO()
            image.save(content, "JPEG", quality=88)
            return ContentFile(content.getvalue()), "jpg", "image"
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise Problem("Файл не является корректной фотографией.") from exc


def safe_video(upload):
    if upload.size > VIDEO_LIMIT:
        raise Problem("Видео должно быть не больше 40 МБ.")
    head = upload.read(4096)
    upload.seek(0)
    is_mp4 = upload.content_type == "video/mp4" and len(head) >= 12 and head[4:8] == b"ftyp"
    is_webm = (
        upload.content_type == "video/webm"
        and head.startswith(b"\x1aE\xdf\xa3")
        and b"webm" in head
    )
    if not (is_mp4 or is_webm):
        raise Problem("Нужен файл MP4 или WebM с корректным заголовком.")
    return upload, "mp4" if is_mp4 else "webm", "video"


def save_asset(upload, *, purpose, resort=None, booking=None, profile=None):
    if not upload or not upload.size:
        raise Problem("Выберите непустой файл.", 422, "media_file_required")
    if upload.content_type in {"image/jpeg", "image/png", "image/webp"}:
        content, extension, kind = safe_image(upload)
    elif purpose == "catalog" and upload.content_type in {"video/mp4", "video/webm"}:
        content, extension, kind = safe_video(upload)
    else:
        raise Problem(
            "Выберите JPEG, PNG или WebP; для каталога также MP4 и WebM.", 422, "media_type_invalid"
        )
    enforce_upload_quota(
        purpose=purpose, incoming_size=content.size, resort=resort, profile=profile, booking=booking
    )
    content_type = "image/jpeg" if kind == "image" else f"video/{extension}"
    content.content_type = content_type
    key = default_storage.save(f"{purpose}/{uuid.uuid4().hex}.{extension}", content)
    try:
        return MediaAsset.objects.create(
            purpose=purpose,
            kind=kind,
            resort=resort,
            booking=booking,
            profile=profile,
            storage_key=key,
            size=content.size,
            content_type=content_type,
        )
    except Exception:
        default_storage.delete(key)
        raise


@method_decorator(bearer_or_csrf_protect, name="dispatch")
@method_decorator(never_cache, name="dispatch")
class MediaUpload(APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    @transaction.atomic
    def post(self, request):
        resort, booking = None, None
        review_upload = bool(request.data.get("bookingId")) or not request.user.is_authenticated
        if not review_upload:
            resort_id = request.data.get("resortId")
            if not resort_id:
                raise Problem("Выберите санаторий для файла.")
            require_staff(request.user, resort_id)
            resort = get_object_or_404(Resort.objects.select_for_update(), pk=resort_id)
            if resort.status == "archived":
                raise Problem("Санаторий в архиве.", 409)
        else:
            booking = review_booking(request, request.data.get("bookingId"))
            if hasattr(booking, "review"):
                raise Problem("Отзыв уже отправлен.", 409)
            resort = Resort.objects.select_for_update().get(pk=booking.resort_id)
        asset = save_asset(
            request.FILES.get("file"),
            purpose="review" if review_upload else "catalog",
            resort=resort,
            booking=booking,
        )
        return Response(
            {"url": asset.url, "kind": asset.kind, "alt": "", "id": asset.pk}, status=201
        )


@method_decorator(bearer_or_csrf_protect, name="dispatch")
@method_decorator(never_cache, name="dispatch")
class ProfileAvatar(APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    @transaction.atomic
    def update(self, request, remove=False):
        from .guest_auth import current_account

        account = current_account(request)
        if not account:
            raise Problem(
                "Войдите в профиль, чтобы изменить фотографию.", 401, "guest_auth_required"
            )
        profile = GuestProfile.objects.select_for_update().get(pk=account.profile_id)
        previous = profile.avatar_id
        asset = (
            None
            if remove
            else save_asset(request.FILES.get("file"), purpose="avatar", profile=profile)
        )
        profile.avatar = asset
        profile.version += 1
        profile.save(update_fields=["avatar", "version", "updated_at"])
        Audit.objects.create(
            actor="Гость сайта",
            entity="guestProfiles",
            entity_id=profile.pk,
            action="avatar-remove" if remove else "avatar-update",
            label="Фотография профиля",
            before={"avatarId": previous},
            after={"avatarId": profile.avatar_id},
        )
        return Response({"profile": guest_profile_data(profile)})

    def post(self, request):
        return self.update(request)

    def delete(self, request):
        return self.update(request, remove=True)


class MediaFile(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        asset = get_object_or_404(
            MediaAsset.objects.select_related("profile", "booking", "resort"), pk=pk
        )
        if not can_read_asset(request, asset):
            raise Http404
        if settings.MEDIA_STORAGE == "supabase":
            response = HttpResponseRedirect(default_storage.url(asset.storage_key, expire=60))
        else:
            try:
                content = default_storage.open(asset.storage_key, "rb")
            except FileNotFoundError as exc:
                raise Http404 from exc
            response = self.local_response(request, asset, content)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'"
        response["Referrer-Policy"] = "no-referrer"
        return response

    @staticmethod
    def local_response(request, asset, content):
        import re

        range_header = request.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=([0-9]{0,20})-([0-9]{0,20})", range_header)
            start, end = 0, asset.size - 1
            if match and (match[1] or match[2]):
                if match[1]:
                    start = int(match[1])
                    end = min(int(match[2]), end) if match[2] else end
                else:
                    start = max(0, asset.size - int(match[2]))
            else:
                start = asset.size
            if start > end or start >= asset.size:
                content.close()
                return HttpResponse(status=416, headers={"Content-Range": f"bytes */{asset.size}"})
            content.seek(start)

            def chunks():
                remaining = end - start + 1
                try:
                    while remaining:
                        chunk = content.read(min(64 * 1024, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk
                finally:
                    content.close()

            if request.method == "HEAD":
                content.close()
                response = HttpResponse(status=206, content_type=asset.content_type)
            else:
                response = StreamingHttpResponse(
                    chunks(), status=206, content_type=asset.content_type
                )
            response["Content-Range"] = f"bytes {start}-{end}/{asset.size}"
            response["Content-Length"] = end - start + 1
        elif request.method == "HEAD":
            content.close()
            response = HttpResponse(content_type=asset.content_type)
            response["Content-Length"] = asset.size
        else:
            response = FileResponse(content, content_type=asset.content_type)
        response["Accept-Ranges"] = "bytes"
        return response
