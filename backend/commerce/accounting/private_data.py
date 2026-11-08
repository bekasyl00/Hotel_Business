"""Authenticated encryption for document identities; keys never derive from auth secrets."""

import json

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings

from booking.errors import Problem


def cipher():
    try:
        keys = settings.DOCUMENT_DATA_ENCRYPTION_KEYS
        if not keys:
            raise ValueError
        return MultiFernet([Fernet(key.encode("ascii")) for key in keys])
    except (ValueError, TypeError, UnicodeError):
        raise Problem(
            "Защищённое хранение реквизитов временно недоступно.",
            503,
            "document_encryption_unavailable",
        ) from None


def seal(data, *, context):
    payload = json.dumps({"context": context, "data": data}, ensure_ascii=False).encode("utf-8")
    return cipher().encrypt(payload).decode("ascii")


def unseal(value, *, context):
    try:
        payload = json.loads(cipher().decrypt(value.encode("ascii")))
        if payload.get("context") != context:
            raise InvalidToken
        return payload["data"]
    except (InvalidToken, ValueError, TypeError, KeyError, UnicodeError):
        raise Problem(
            "Реквизиты документа временно недоступны. Обратитесь к администратору.",
            503,
            "document_data_unavailable",
        ) from None
