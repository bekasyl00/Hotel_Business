from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_handler


class Problem(APIException):
    def __init__(self, message, status=422, code=None):
        self.status_code = status
        self.machine_code = code
        super().__init__(message)


def exception_handler(exc, context):
    if isinstance(exc, ProtectedError):
        return Response(
            {
                "message": "Запись используется в истории бронирований. Отключите её вместо удаления."
            },
            status=409,
        )
    if isinstance(exc, IntegrityError):
        return Response(
            {"message": "Конфликт данных: номер уже занят или запись с такими данными существует."},
            status=409,
        )
    if isinstance(exc, DjangoValidationError):
        return Response({"message": " ".join(exc.messages)}, status=422)
    response = drf_handler(exc, context)
    if response is not None:
        if response.status_code == 400:
            response.status_code = 422
        fields = response.data if isinstance(response.data, dict) else {}
        response.data = {
            "message": str(fields.get("detail", "Проверьте заполнение полей.")),
            "fields": fields,
        }
        if getattr(exc, "machine_code", None):
            response.data["code"] = exc.machine_code
    return response
