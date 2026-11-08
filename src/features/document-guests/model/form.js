export const documentGuestFields = [
  "fullName",
  "iin",
  "address",
  "phone",
  "iban",
  "bank",
  "bik",
];
const limits = {
  fullName: 160,
  iin: 12,
  address: 240,
  phone: 32,
  iban: 20,
  bank: 100,
  bik: 11,
};

export function documentGuest(row = {}) {
  return Object.fromEntries(
    documentGuestFields.map((key) => [
      key,
      typeof row?.[key] === "string" ? row[key] : "",
    ]),
  );
}

export function documentGuestsForm(data, leadName = "") {
  if (
    !Number.isInteger(data?.version) ||
    data.version < 0 ||
    !Number.isInteger(data.expectedGuests) ||
    data.expectedGuests < 1 ||
    data.expectedGuests > 4 ||
    !Array.isArray(data.guests) ||
    data.guests.length > 4
  )
    throw new Error("invalidResponse");
  const guests = data.guests.map(documentGuest);
  while (guests.length < data.expectedGuests) guests.push(documentGuest());
  if (data.version === 0 && !guests[0].fullName) guests[0].fullName = leadName;
  return {
    version: data.version,
    expectedGuests: data.expectedGuests,
    buyerIndex: data.buyerIndex ?? null,
    guests,
  };
}

export function documentGuestsPayload(form) {
  return {
    version: form.version,
    buyerIndex: form.buyerIndex,
    guests: form.guests.map((row) =>
      Object.fromEntries(
        documentGuestFields.map((key) => [key, row[key].trim()]),
      ),
    ),
  };
}

export function validateDocumentGuests(form) {
  if (
    !Array.isArray(form?.guests) ||
    !form.guests.length ||
    form.guests.length > 4
  )
    return { key: "invalidGuests" };
  if (
    form.buyerIndex !== null &&
    (!Number.isInteger(form.buyerIndex) ||
      form.buyerIndex < 0 ||
      form.buyerIndex >= form.guests.length)
  )
    return { key: "invalidBuyer" };
  for (const [index, guest] of form.guests.entries()) {
    const fields = documentGuest(guest);
    const error = (key) => ({ key, number: index + 1 });
    if (
      documentGuestFields.some((key) => fields[key].trim().length > limits[key])
    )
      return error("tooLong");
    if (fields.iin && !/^[0-9]{12}$/.test(fields.iin.trim()))
      return error("invalidIin");
    if (fields.iban && !/^KZ[A-Z0-9]{18}$/.test(fields.iban.trim()))
      return error("invalidIban");
    if (fields.bik && !/^[A-Z0-9]{8}(?:[A-Z0-9]{3})?$/.test(fields.bik.trim()))
      return error("invalidBik");
  }
  return null;
}
