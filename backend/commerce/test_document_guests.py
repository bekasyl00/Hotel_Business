import json
from io import BytesIO

from cryptography.fernet import Fernet
from django.test import TestCase, override_settings
from openpyxl import load_workbook
from rest_framework.test import APIClient

from booking.models import Audit, GuestAccount, GuestProfile, User
from booking.serializers import booking_data
from commerce.accounting.document_guests import require_complete_roster
from commerce.accounting.private_data import seal, unseal
from commerce.accounting.rendering import pdf_bytes, xlsx_bytes
from commerce.accounting.services import prepare_document
from commerce.models import DocumentGuestRoster
from commerce.test_document_helpers import document_key, fictional_guests
from commerce.tests import fixture


class DocumentGuestTests(TestCase):
    def setUp(self):
        document_key(self)
        self.resort, self.booking, self.manager = fixture()
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.manager)
        self.token = self.client.get("/api/auth/csrf").json()["token"]
        self.path = f"/api/bookings/{self.booking.pk}/document-guests"
        self.payload = {"version": 0, **fictional_guests(self.booking)}

    def save(self, body=None):
        return self.client.put(
            self.path, body or self.payload, format="json", HTTP_X_CSRFTOKEN=self.token
        )

    def test_scoping_csrf_validation_and_partial_drafts(self):
        empty = self.client.get(self.path).json()
        self.assertEqual((empty["version"], empty["expectedGuests"]), (0, self.booking.guests))
        self.assertFalse(empty["complete"])
        self.assertEqual(self.client.put(self.path, self.payload, format="json").status_code, 403)
        invalid = {**self.payload, "guests": [{"fullName": "Fiction", "iin": "123456"}]}
        self.assertEqual(self.save(invalid).status_code, 422)
        self.assertEqual(self.save({**self.payload, "passport": "unneeded"}).status_code, 422)
        self.assertEqual(self.save({**self.payload, "buyerIndex": 99}).status_code, 422)
        partial = self.save({"version": 0, "buyerIndex": None, "guests": [{"fullName": ""}]})
        self.assertEqual(partial.status_code, 200, partial.content)
        self.assertFalse(partial.json()["complete"])
        self.assertEqual(self.save().status_code, 409)
        self.assertEqual(self.save({**self.payload, "version": 1}).status_code, 200)
        other = User.objects.create_user(username="other-doc-staff", role="manager")
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.assertEqual(self.save({**self.payload, "version": 2}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.path).status_code, 401)

    def test_encrypted_at_rest_not_in_booking_workspace_or_audit(self):
        self.assertEqual(self.save().status_code, 200)
        row = DocumentGuestRoster.objects.get(booking=self.booking)
        guest = self.payload["guests"][0]
        self.assertNotIn(guest["iin"], row.ciphertext)
        self.assertNotIn(guest["fullName"], row.ciphertext)
        self.assertEqual(self.client.get(self.path).json()["guests"], self.payload["guests"])
        public = json.dumps(booking_data(self.booking), ensure_ascii=False)
        audit = json.dumps(list(Audit.objects.values("before", "after")), ensure_ascii=False)
        workspace = self.client.get("/api/workspace").content.decode()
        for output in (public, audit, workspace):
            self.assertNotIn(guest["iin"], output)
            self.assertNotIn(guest["fullName"], output)
        self.assertNotIn("ciphertext", workspace)

    def test_accountant_and_guest_owner_cannot_access_document_identities(self):
        accountant = User.objects.create_user(username="doc-accountant", role="accountant")
        self.client.force_login(accountant)
        self.token = self.client.get("/api/auth/csrf").json()["token"]
        self.assertEqual(self.save().status_code, 403)
        self.assertEqual(self.client.get(self.path).status_code, 403)
        guest = APIClient()
        session = guest.session
        session["guest_owner"] = self.booking.owner
        session.save()
        self.assertEqual(guest.get(self.path).status_code, 401)

    def test_all_three_templates_use_selected_buyer_and_snapshots_are_frozen(self):
        self.payload["buyerIndex"] = 1
        buyer = self.payload["guests"][1]
        original_name = buyer["fullName"]
        buyer.update(iban="KZ" + "0" * 18, bank="Вымышленный банк", bik="FAKEKZ00")
        self.assertEqual(self.save().status_code, 200)
        for kind in ("act", "invoice", "cash_order"):
            doc = prepare_document(self.booking, kind, self.manager)
            self.assertNotIn(buyer["iin"], json.dumps(doc.snapshot))
            wb = load_workbook(BytesIO(xlsx_bytes(doc)))
            ws = wb.active
            if kind == "invoice":
                self.assertIn(buyer["iin"], ws["A21"].value)
                self.assertIn(buyer["iban"], ws["A22"].value)
            elif kind == "act":
                self.assertEqual(ws["AQ9"].value, buyer["iin"])
                self.assertIn(buyer["address"], ws["E9"].value)
            else:
                self.assertEqual(ws["D19"].value, buyer["fullName"])
                self.assertEqual(ws["O14"].value, buyer["fullName"])
            self.assertTrue(pdf_bytes(doc).startswith(b"%PDF"))
            doc.state = "released"
            doc.save()
            self.assertNotIn(self.payload["guests"][0]["fullName"], str(list(ws.values)))
        self.payload["guests"][1]["fullName"] = "Изменённый плательщик"
        self.assertEqual(self.save({**self.payload, "version": 1}).status_code, 200)
        self.assertEqual(load_workbook(BytesIO(xlsx_bytes(doc))).active["D19"].value, original_name)

    def test_missing_wrong_keys_fail_closed_and_keyring_supports_rotation(self):
        self.assertEqual(self.save().status_code, 200)
        with override_settings(DOCUMENT_DATA_ENCRYPTION_KEYS=[]):
            self.assertEqual(self.client.get(self.path).status_code, 503)
            self.assertEqual(self.save({**self.payload, "version": 1}).status_code, 503)
        with override_settings(DOCUMENT_DATA_ENCRYPTION_KEYS=[Fernet.generate_key().decode()]):
            self.assertEqual(self.client.get(self.path).status_code, 503)
        from django.conf import settings

        old = settings.DOCUMENT_DATA_ENCRYPTION_KEYS[0]
        with override_settings(DOCUMENT_DATA_ENCRYPTION_KEYS=[Fernet.generate_key().decode(), old]):
            self.assertEqual(self.client.get(self.path).status_code, 200)
            self.assertEqual(self.save({**self.payload, "version": 1}).status_code, 200)
        token = seal({"fiction": "only"}, context="one")
        from booking.errors import Problem

        with self.assertRaises(Problem):
            unseal(token, context="other")

    def test_completeness_requires_each_occupant_and_selected_buyer_address(self):
        from booking.errors import Problem

        for field in ("fullName", "iin", "address"):
            data = fictional_guests(self.booking)
            data["guests"][0][field] = ""
            version = DocumentGuestRoster.objects.filter(booking=self.booking).first()
            response = self.save({"version": version.version if version else 0, **data})
            self.assertEqual(response.status_code, 200, response.content)
            with self.assertRaises(Problem) as failure:
                require_complete_roster(self.booking)
            self.assertEqual(failure.exception.machine_code, "document_guests_incomplete")
        row = DocumentGuestRoster.objects.get(booking=self.booking)
        self.assertEqual(self.save({**self.payload, "version": row.version}).status_code, 200)
        require_complete_roster(self.booking)

    def test_same_booking_roster_is_shared_between_staff_sessions_and_api_versions(self):
        saved = self.save()
        self.assertEqual(saved.status_code, 200)
        admin = User.objects.create_user(username="document-platform-admin", role="admin")
        other = APIClient(enforce_csrf_checks=True)
        other.force_login(admin)
        token = other.get("/api/auth/csrf").json()["token"]
        versioned_path = self.path.replace("/api/", "/api/v1/")
        self.assertEqual(other.get(versioned_path).json(), saved.json())
        updated = {**self.payload, "version": 1, "buyerIndex": 1}
        changed = other.put(versioned_path, updated, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual(self.client.get(self.path).json(), changed.json())
        self.assertEqual(DocumentGuestRoster.objects.filter(booking=self.booking).count(), 1)
        self.assertEqual(self.save({**self.payload, "version": 1}).status_code, 409)

    def linked_account(self):
        profile = GuestProfile.objects.create(
            owner=self.booking.owner, name="Имя из профиля", phone="+77010000031"
        )
        account = GuestAccount.objects.create(profile=profile, phone=profile.phone, password="!")
        self.booking.guest_profile = profile
        self.booking.save(update_fields=["guest_profile"])
        return account

    def test_registered_primary_contacts_are_authoritative_but_companions_are_editable(self):
        account = self.linked_account()
        first = self.client.get(self.path).json()
        self.assertEqual(
            first["primaryGuest"],
            {"index": 0, "source": "profile", "lockedFields": ["fullName", "phone"]},
        )
        self.assertEqual(first["guests"][0]["fullName"], account.profile.name)
        self.assertEqual(first["guests"][0]["phone"], account.phone)
        self.payload["guests"][0].update(fullName="Подмена имени", phone="+77010000099")
        self.payload["buyerIndex"] = 1
        saved = self.save()
        self.assertEqual(saved.status_code, 200, saved.content)
        data = saved.json()
        self.assertEqual(data["guests"][0]["fullName"], account.profile.name)
        self.assertEqual(data["guests"][0]["phone"], account.phone)
        self.assertEqual(data["guests"][0]["iin"], self.payload["guests"][0]["iin"])
        self.assertEqual(data["guests"][1], self.payload["guests"][1])
        self.assertEqual(data["buyerIndex"], 1)
        row = DocumentGuestRoster.objects.get(booking=self.booking)
        stored = unseal(row.ciphertext, context=f"roster:{self.booking.pk}")
        self.assertEqual(stored["guests"], data["guests"])
        self.assertNotIn("primaryGuest", stored)

    def test_profile_changes_refresh_roster_but_never_rewrite_frozen_buyer(self):
        account = self.linked_account()
        self.assertEqual(self.save().status_code, 200)
        doc = prepare_document(self.booking, "act", self.manager)
        original = doc.snapshot.copy()
        doc.state = "released"
        doc.save(update_fields=["state"])
        account.profile.name = "Обновлённый профиль"
        account.profile.save(update_fields=["name"])
        roster = self.client.get(self.path).json()
        self.assertEqual(roster["guests"][0]["fullName"], account.profile.name)
        self.assertEqual(roster["version"], 1)
        doc.refresh_from_db()
        self.assertEqual(doc.snapshot, original)
        buyer = unseal(
            doc.snapshot["buyerEncrypted"], context=f"buyer:{self.booking.pk}:{doc.number}"
        )
        self.assertEqual(buyer["fullName"], "Имя из профиля")

    def test_manual_booking_contacts_remain_editable_without_phone_linking(self):
        self.booking.guest_phone = "+77010000032"
        self.booking.source = "staff"
        self.booking.save(update_fields=["guest_phone", "source"])
        unrelated = GuestProfile.objects.create(
            owner="unrelated-profile-owner", name="Чужой профиль", phone=self.booking.guest_phone
        )
        GuestAccount.objects.create(profile=unrelated, phone="+77010000032", password="!")
        first = self.client.get(self.path).json()
        self.assertEqual(
            first["primaryGuest"], {"index": 0, "source": "manual", "lockedFields": []}
        )
        self.assertEqual(first["guests"][0]["fullName"], self.booking.guest_label)
        saved = self.save().json()
        self.assertEqual(saved["guests"], self.payload["guests"])

    def test_unrelated_linked_profile_never_supplies_primary_identity(self):
        account = self.linked_account()
        account.profile.owner = "other-owner"
        account.profile.save(update_fields=["owner"])
        data = self.client.get(self.path).json()
        self.assertEqual(data["primaryGuest"]["source"], "manual")
        self.assertNotEqual(data["guests"][0]["fullName"], account.profile.name)
