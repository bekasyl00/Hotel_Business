from cryptography.fernet import Fernet
from django.test import override_settings

from commerce.accounting.private_data import seal
from commerce.models import DocumentGuestRoster


def document_key(test):
    context = override_settings(DOCUMENT_DATA_ENCRYPTION_KEYS=[Fernet.generate_key().decode()])
    context.enable()
    test.addCleanup(context.disable)


def fictional_guests(booking):
    return {
        "buyerIndex": 0,
        "guests": [
            {
                "fullName": f"Вымышленный Гость {index + 1}",
                "iin": str(index).zfill(12),
                "address": "Вымышленный адрес",
                "phone": "",
                "iban": "",
                "bank": "",
                "bik": "",
            }
            for index in range(booking.guests)
        ],
    }


def complete_roster(booking, user):
    return DocumentGuestRoster.objects.create(
        booking=booking,
        updated_by=user,
        ciphertext=seal(fictional_guests(booking), context=f"roster:{booking.pk}"),
    )
