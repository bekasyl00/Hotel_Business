import uuid

from django.test import TestCase
from rest_framework.test import APIClient

from booking.models import Resort

from .models import DemoPayment
from .services import apply_cancellation
from .tests import fixture


class ReceiptTests(TestCase):
    def setUp(self):
        self.resort, self.booking, self.manager = fixture()
        self.client = APIClient(enforce_csrf_checks=True)
        self.token = self.client.get("/api/auth/csrf").json()["token"]
        session = self.client.session
        session["guest_owner"] = self.booking.owner
        session.save()

    def pay(self, outcome="success"):
        result = self.client.post(
            "/api/payments/demo",
            {"bookingId": self.booking.pk, "requestId": str(uuid.uuid4()), "outcome": outcome},
            format="json",
            HTTP_X_CSRFTOKEN=self.token,
        )
        self.assertEqual(result.status_code, 200, result.content)
        return result.json()

    def test_receipt_snapshot_and_no_phone_or_provider_claim(self):
        self.booking.guest_phone = "+70000000000"
        self.booking.save()
        paid = self.pay()
        self.assertEqual(paid["receiptUrl"], "/receipts/" + paid["id"])
        response = self.client.get("/api" + paid["receiptUrl"])
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        receipt = response.json()["receipt"]
        self.assertEqual(receipt["source"], "demo")
        self.assertEqual(receipt["total"], 36000)
        self.assertIn("не фискальный", receipt["notice"])
        self.assertNotContains(response, self.booking.guest_phone)
        self.assertNotIn("guestPhone", receipt)
        self.assertFalse(receipt["legacySnapshot"])
        self.assertEqual(DemoPayment.objects.get().receipt, receipt)
        self.resort.name, self.resort.address = "Изменённый санаторий", "Новый адрес"
        self.resort.save()
        self.booking.guest_label = "Другой гость"
        self.booking.save()
        self.assertEqual(self.client.get("/api" + paid["receiptUrl"]).json()["receipt"], receipt)

    def test_receipt_access_and_failed_attempts(self):
        failed = self.pay("failed")
        self.assertIsNone(failed["receiptUrl"])
        self.assertEqual(self.client.get("/api/receipts/" + failed["id"]).status_code, 404)
        paid = self.pay()
        url = "/api" + paid["receiptUrl"]
        stranger = APIClient()
        self.assertEqual(stranger.get(url).status_code, 404)
        self.assertEqual(stranger.get(url + "/pdf").status_code, 404)
        stranger.force_login(self.manager)
        self.assertEqual(stranger.get(url).status_code, 200)
        other = Resort.objects.create(name="Другой", city="Тест", address="Тест", lat=40, lng=70)
        self.manager.resort = other
        self.manager.save()
        self.assertEqual(stranger.get(url).status_code, 404)
        self.manager.role = "admin"
        self.manager.save()
        self.assertEqual(stranger.get(url).status_code, 200)

    def test_receipt_pdf_attachment_has_embedded_unicode_font(self):
        paid = self.pay()
        response = self.client.get("/api" + paid["receiptUrl"] + "/pdf")
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn(".pdf", response["Content-Disposition"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertIn(b"/FontFile2", response.content)
        self.assertIn(b"/ToUnicode", response.content)
        self.assertIn(b"NotoSans", response.content)
        from reportlab.pdfbase import pdfmetrics

        cmap = pdfmetrics.getFont("TynysNoto").face.charToGlyph
        self.assertTrue(all(ord(char) in cmap for char in "ТынысОплата₸"))

    def test_refund_does_not_rewrite_original_receipt(self):
        paid = self.pay()
        url = "/api" + paid["receiptUrl"]
        original = self.client.get(url).json()["receipt"]
        result = apply_cancellation(self.booking, self.manager, staff=True)
        after = self.client.get(url).json()
        self.assertEqual(after["receipt"], original)
        self.assertEqual(after["payment"]["status"], "refunded")
        self.assertEqual(after["refund"]["amount"], result["refundAmount"])
        self.assertEqual(after["receipt"]["total"], 36000)
        self.assertEqual(self.client.get(url + "/pdf").status_code, 200)

    def test_legacy_receipt_is_frozen_on_first_authorized_read(self):
        paid = self.pay()
        DemoPayment.objects.filter(pk=paid["id"]).update(receipt={})
        self.resort.address = "Адрес при восстановлении"
        self.resort.save()
        url = "/api" + paid["receiptUrl"]
        original = self.client.get(url).json()["receipt"]
        self.assertTrue(original["legacySnapshot"])
        self.assertEqual(original["resortAddress"], "Адрес при восстановлении")
        self.resort.address = "Последующее изменение"
        self.resort.save()
        self.assertEqual(self.client.get(url).json()["receipt"], original)
