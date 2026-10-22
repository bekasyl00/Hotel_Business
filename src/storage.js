const KEY = "tynys:bookings:v1";
const validDate = (value) =>
  typeof value === "string" &&
  /^\d{4}-\d{2}-\d{2}$/.test(value) &&
  Number.isFinite(Date.parse(value)) &&
  new Date(value).toISOString().slice(0, 10) === value;
const valid = (b) =>
  b &&
  [
    "id",
    "resortId",
    "resortName",
    "roomId",
    "roomName",
    "unit",
    "tariffId",
    "tariffName",
  ].every((key) => typeof b[key] === "string") &&
  validDate(b.start) &&
  validDate(b.end) &&
  b.end > b.start &&
  ["confirmed", "cancelled"].includes(b.status) &&
  Number.isFinite(b.total) &&
  b.total >= 0 &&
  Number.isInteger(b.guests) &&
  b.guests >= 1 &&
  b.guests <= 4;
export function readBookings() {
  const raw = localStorage.getItem(KEY);
  if (!raw) return [];
  const value = JSON.parse(raw);
  if (!Array.isArray(value) || !value.every(valid))
    throw new Error(
      "Локальные бронирования повреждены. Откройте сайт в другом профиле браузера или восстановите его локальные данные.",
    );
  return value;
}
export function writeBookings(bookings) {
  localStorage.setItem(KEY, JSON.stringify(bookings));
}
export const storageKey = KEY;
