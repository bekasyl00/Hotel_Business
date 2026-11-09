import test from "node:test";
import assert from "node:assert/strict";
import {
  documentGuest,
  documentGuestsForm,
  documentGuestsPayload,
  validateDocumentGuests,
} from "../src/features/document-guests/model/form.js";

test("document drafts keep one row per resident and allow incomplete requisites", () => {
  const form = documentGuestsForm(
    { version: 0, expectedGuests: 2, buyerIndex: null, guests: [] },
    "QA Guest",
  );
  assert.equal(form.guests.length, 2);
  assert.equal(form.guests[0].fullName, "QA Guest");
  assert.equal(form.guests[1].fullName, "");
  assert.equal(validateDocumentGuests(form), null);
  assert.equal(form.buyerIndex, null);
  assert.equal(documentGuestsPayload(form).version, 0);
});

test("saved guest rows are copied without reusing a booking profile or unknown fields", () => {
  const row = {
    fullName: "Saved guest",
    iin: "000000000000",
    secret: "never transport",
    accountId: "private",
  };
  const form = documentGuestsForm(
    { version: 3, expectedGuests: 1, buyerIndex: 0, guests: [row] },
    "Changed profile name",
  );
  assert.equal(form.guests[0].fullName, "Saved guest");
  form.guests[0].fullName = "Edited draft";
  assert.equal(row.fullName, "Saved guest");
  assert.deepEqual(Object.keys(documentGuestsPayload(form)).sort(), [
    "buyerIndex",
    "guests",
    "version",
  ]);
  const fields = documentGuestsPayload(form).guests[0];
  assert.equal("secret" in fields, false);
  assert.equal("accountId" in fields, false);
  assert.equal("birthDate" in fields, false);
  assert.equal(fields.iin, "000000000000");
});

test("staff document IIN validates twelve digits without inferring age or identity", () => {
  const form = documentGuestsForm({
    version: 1,
    expectedGuests: 1,
    buyerIndex: 0,
    guests: [documentGuest({ fullName: "QA Guest", iin: "000000000000" })],
  });
  assert.equal(validateDocumentGuests(form), null);
  for (const iin of ["000000", "00000000000X", "００００００００００００"]) {
    form.guests[0].iin = iin;
    assert.equal(validateDocumentGuests(form).key, "invalidIin");
  }
  form.guests[0].iin = "";
  assert.equal(validateDocumentGuests(form), null);
});

test("payer selection and optional bank fields must refer to valid draft data", () => {
  const form = documentGuestsForm({
    version: 2,
    expectedGuests: 1,
    buyerIndex: 0,
    guests: [documentGuest({ iban: "KZ000000000000000000", bik: "FAKEKZ00" })],
  });
  assert.equal(validateDocumentGuests(form), null);
  form.buyerIndex = 1;
  assert.equal(validateDocumentGuests(form).key, "invalidBuyer");
  form.buyerIndex = 0;
  form.guests[0].iban = "KZ123";
  assert.equal(validateDocumentGuests(form).key, "invalidIban");
  form.guests[0].iban = "";
  form.guests[0].bik = "SHORT";
  assert.equal(validateDocumentGuests(form).key, "invalidBik");
});

test("malformed or unversioned server responses are not editable as a new document draft", () => {
  for (const invalid of [
    null,
    {},
    { version: -1, expectedGuests: 1, guests: [] },
    { version: 0, expectedGuests: 0, guests: [] },
    { version: 0, expectedGuests: 5, guests: [] },
    { version: 0, expectedGuests: 1, guests: "invalid" },
  ]) {
    assert.throws(() => documentGuestsForm(invalid));
  }
});

test("document roster responses must belong to the requested booking", () => {
  const data = {
    bookingId: "booking-a",
    version: 3,
    expectedGuests: 2,
    guests: [documentGuest({ fullName: "Saved resident" })],
    buyerIndex: 0,
  };
  assert.equal(
    documentGuestsForm(data, "", "booking-a").guests[0].fullName,
    "Saved resident",
  );
  assert.throws(
    () => documentGuestsForm(data, "", "booking-b"),
    /invalidResponse/,
  );
  assert.throws(
    () =>
      documentGuestsForm({ ...data, bookingId: undefined }, "", "booking-a"),
    /invalidResponse/,
  );
});

test("linked primary contacts use the server profile without a stale booking-name fallback", () => {
  const primaryGuest = {
    index: 0,
    source: "profile",
    lockedFields: ["fullName", "phone"],
  };
  const data = {
    bookingId: "booking-a",
    version: 0,
    expectedGuests: 2,
    buyerIndex: 1,
    primaryGuest,
    guests: [
      documentGuest({ fullName: "Profile guest", phone: "+77000000000" }),
      documentGuest({ fullName: "Companion", phone: "+77000000001" }),
    ],
  };
  const form = documentGuestsForm(data, "Old booking label", "booking-a");
  assert.equal(form.guests[0].fullName, "Profile guest");
  assert.equal(form.guests[0].phone, "+77000000000");
  assert.deepEqual(form.primaryGuest, primaryGuest);
  assert.notEqual(form.primaryGuest.lockedFields, primaryGuest.lockedFields);
  form.guests[1].fullName = "Edited companion";
  form.guests[1].phone = "+77000000002";
  const payload = documentGuestsPayload(form);
  assert.equal("primaryGuest" in payload, false);
  assert.equal(payload.buyerIndex, 1);
  assert.equal(payload.guests[1].fullName, "Edited companion");
  assert.equal(payload.guests[1].phone, "+77000000002");
  assert.equal(data.guests[1].fullName, "Companion");

  data.guests[0].fullName = "";
  assert.equal(
    documentGuestsForm(data, "Stale name", "booking-a").guests[0].fullName,
    "",
    "a missing profile contact must not be replaced with a booking label",
  );
});

test("manual and legacy bookings keep editable primary contacts", () => {
  for (const primaryGuest of [
    undefined,
    { index: 0, source: "manual", lockedFields: [] },
  ]) {
    const form = documentGuestsForm(
      { version: 0, expectedGuests: 1, guests: [], primaryGuest },
      "Manually entered guest",
    );
    assert.equal(form.primaryGuest.source, "manual");
    assert.deepEqual(form.primaryGuest.lockedFields, []);
    assert.equal(form.guests[0].fullName, "Manually entered guest");
    form.guests[0].fullName = "Corrected name";
    form.guests[0].phone = "+77000000003";
    assert.equal(
      documentGuestsPayload(form).guests[0].fullName,
      "Corrected name",
    );
    assert.equal(documentGuestsPayload(form).guests[0].phone, "+77000000003");
  }
});

test("malformed profile-lock metadata fails closed instead of making contacts editable", () => {
  for (const primaryGuest of [
    null,
    { index: 1, source: "profile", lockedFields: ["fullName", "phone"] },
    { index: 0, source: "unknown", lockedFields: [] },
    { index: 0, source: "profile", lockedFields: ["fullName"] },
    { index: 0, source: "profile", lockedFields: ["iin", "phone"] },
    { index: 0, source: "manual", lockedFields: ["fullName", "phone"] },
  ]) {
    assert.throws(
      () =>
        documentGuestsForm({
          version: 0,
          expectedGuests: 1,
          guests: [],
          primaryGuest,
        }),
      /invalidResponse/,
    );
  }
});
