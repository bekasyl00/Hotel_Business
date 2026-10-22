import io
import uuid
import warnings

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .errors import Problem
from .models import Resort
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


@method_decorator(csrf_protect, name="dispatch")
class MediaUpload(APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        review_upload = bool(request.data.get("bookingId")) or not request.user.is_authenticated
        if not review_upload:
            resort_id = request.data.get("resortId")
            if not resort_id:
                raise Problem("Выберите санаторий для файла.")
            require_staff(request.user, resort_id)
            resort = get_object_or_404(Resort, pk=resort_id)
            if resort.status == "archived":
                raise Problem("Санаторий в архиве.", 409)
            folder = f"catalog/{resort.pk}"
        else:
            booking = review_booking(request, request.data.get("bookingId"))
            if hasattr(booking, "review"):
                raise Problem("Отзыв уже отправлен.", 409)
            folder = "reviews"
        upload = request.FILES.get("file")
        if not upload or not upload.size:
            raise Problem("Выберите непустой файл.")
        if upload.content_type in {"image/jpeg", "image/png", "image/webp"}:
            content, extension, kind = safe_image(upload)
        elif not review_upload and upload.content_type in {"video/mp4", "video/webm"}:
            content, extension, kind = safe_video(upload)
        else:
            raise Problem("Гостям доступны JPEG, PNG и WebP; сотрудникам также MP4 и WebM.")
        name = default_storage.save(f"{folder}/{uuid.uuid4().hex}.{extension}", content)
        return Response({"url": default_storage.url(name), "kind": kind, "alt": ""}, status=201)
