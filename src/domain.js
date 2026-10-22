export const money = (amount) =>
  new Intl.NumberFormat("ru-KZ").format(amount) + " ₸";
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
    return "Укажите корректные даты заезда и выезда.";
  if (start < today) return "Дата заезда не может быть в прошлом.";
  if (end <= start) return "Выезд должен быть позже заезда.";
  if (nightsBetween(start, end) > 30)
    return "В демоверсии можно выбрать до 30 ночей.";
  if (!Number.isInteger(guests) || guests < 1 || guests > 4)
    return "Выберите от 1 до 4 гостей.";
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
          b.status !== "cancelled" &&
          overlaps(search, b),
      ),
  );
}
export function quote(room, tariff, search) {
  const nights = nightsBetween(search.start, search.end);
  const nightly = room.price + tariff.supplement * search.guests;
  return { nights, nightly, total: nightly * nights };
}
export function reserve({ resort, room, tariff, search, reservations }) {
  const error = validateSearch(search);
  if (error) throw new Error(error);
  if (!resort.rooms.some((r) => r.id === room.id))
    throw new Error("Номер не найден. Повторите выбор.");
  const unit = availableUnits(room, search, reservations)[0];
  if (!unit)
    throw new Error(
      "Этот номер уже занят на выбранные даты. Выберите другой номер.",
    );
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
    status: "confirmed",
    createdAt: new Date().toISOString(),
  };
}
