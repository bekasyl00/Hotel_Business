import { t } from "../../../shared/i18n/index.js";
export { money } from "../../../shared/lib/index.js";
export function dateAfter(days = 0, now = new Date()) {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
export function nightsBetween(start, end) {
  return Math.round((Date.parse(end) - Date.parse(start)) / 86400000);
}
export function validateSearch({ start, end, guests }, today = dateAfter()) {
  const validDate = (value) =>
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    Number.isFinite(Date.parse(value)) &&
    new Date(value).toISOString().slice(0, 10) === value;
  if (!validDate(start) || !validDate(end))
    return t("common.booking.invalidDates");
  if (start < today) return t("common.booking.past");
  if (end <= start) return t("common.booking.order");
  if (nightsBetween(start, end) > 30) return t("common.booking.maxNights");
  if (!Number.isInteger(guests) || guests < 1 || guests > 4)
    return t("common.booking.guests");
  return "";
}
export const overlaps = (a, b) => a.start < b.end && b.start < a.end;
export function availableUnits(room, search, reservations) {
  if (search.guests > room.capacity) return [];
  return room.units.filter(
    (unit) =>
      !reservations.some(
        (b) =>
          b.roomId === room.id &&
          b.unit === unit &&
          ["pending", "confirmed"].includes(b.status) &&
          overlaps(search, b),
      ),
  );
}
export function quote(room, tariff, search) {
  const { nights, nightly, total } = quoteStay(room, tariff, search);
  return { nights, nightly, total };
}
export function validatePricePeriods(periods) {
  if (!Array.isArray(periods) || periods.length > 60)
    return t("common.pricing.invalidPeriods");
  const validDate = (value) =>
    typeof value === "string" &&
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    Number.isFinite(Date.parse(value)) &&
    new Date(value).toISOString().slice(0, 10) === value;
  const sorted = [...periods].sort((a, b) =>
    String(a?.start).localeCompare(String(b?.start)),
  );
  for (let i = 0; i < sorted.length; i++) {
    const p = sorted[i];
    if (
      !p ||
      typeof p.label !== "string" ||
      !p.label.trim() ||
      p.label.length > 80 ||
      !validDate(p.start) ||
      !validDate(p.end) ||
      p.end <= p.start ||
      !Number.isInteger(p.price) ||
      p.price < 0 ||
      p.price > 10000000
    )
      return t("common.pricing.invalidPeriods");
    if (i && sorted[i - 1].end > p.start) return t("common.pricing.overlap");
  }
  return "";
}
export function validateChildren(guests, childrenAges = []) {
  return !Array.isArray(childrenAges) ||
    childrenAges.length >= guests ||
    childrenAges.length > 3 ||
    childrenAges.some((age) => !Number.isInteger(age) || age < 0 || age > 17)
    ? t("common.pricing.invalidChildren")
    : "";
}
export function quoteStay(room, tariff, search) {
  const count = nightsBetween(search.start, search.end);
  if (
    !Number.isInteger(count) ||
    count < 1 ||
    count > 30 ||
    !Number.isInteger(search.guests) ||
    search.guests < 1 ||
    search.guests > 4 ||
    validateChildren(search.guests, search.childrenAges)
  )
    return null;
  const childrenAges = search.childrenAges || [];
  const freeChildren = tariff.childrenUnderThreeFree
    ? childrenAges.filter((age) => age < 3).length
    : 0;
  const chargeableGuests = search.guests - freeChildren;
  const discountPercent =
    tariff.priceKind === "discount" ? tariff.discountPercent : 0;
  const nightlyBreakdown = Array.from({ length: count }, (_, i) => {
    const date = new Date(Date.parse(search.start) + i * 86400000)
      .toISOString()
      .slice(0, 10);
    const period = (room.pricePeriods || []).find(
      (p) => p.start <= date && date < p.end,
    );
    const roomPrice = period ? period.price : room.price;
    const supplementTotal = tariff.supplement * chargeableGuests;
    const regularNightly = roomPrice + supplementTotal;
    return {
      date,
      roomPrice,
      periodLabel: period?.label || "",
      supplementTotal,
      regularNightly,
      nightly: Math.floor(
        (regularNightly * (100 - discountPercent) + 50) / 100,
      ),
    };
  });
  const uniform = (key) =>
    nightlyBreakdown.every((line) => line[key] === nightlyBreakdown[0][key])
      ? nightlyBreakdown[0][key]
      : null;
  return {
    pricingVersion: 2,
    childrenAges: [...childrenAges],
    childrenUnderThreeFree: !!tariff.childrenUnderThreeFree,
    freeChildren,
    chargeableGuests,
    priceKind: tariff.priceKind || "regular",
    discountPercent,
    nightlyBreakdown,
    nightly: uniform("nightly"),
    regularNightly: uniform("regularNightly"),
    nights: count,
    total: nightlyBreakdown.reduce((sum, line) => sum + line.nightly, 0),
  };
}
export function reserve({ resort, room, tariff, search, reservations }) {
  const error = validateSearch(search);
  if (error) throw new Error(error);
  if (!resort.rooms.some((r) => r.id === room.id))
    throw new Error(t("common.booking.missingRoom"));
  const unit = availableUnits(room, search, reservations)[0];
  if (!unit) throw new Error(t("common.booking.occupied"));
  return {
    id: crypto.randomUUID(),
    resortId: resort.id,
    resortName: resort.name,
    roomId: room.id,
    roomName: room.title,
    unit,
    tariffId: tariff.id,
    tariffName: tariff.name,
    ...search,
    ...quote(room, tariff, search),
    status: "pending",
    createdAt: new Date().toISOString(),
  };
}
