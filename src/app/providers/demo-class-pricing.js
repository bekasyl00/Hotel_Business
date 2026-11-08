import { validatePricePeriods } from "../../entities/booking/rules.js";
import { ApiError } from "../../shared/api/index.js";

const fail = (message, status = 422) => {
  throw new ApiError(message, status);
};
const strict = (value, fields) => {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.keys(value).some((key) => !fields.includes(key))
  )
    fail("Неизвестные поля запроса.");
};

export function demoClassPricing({
  db,
  method,
  pathname,
  params,
  payload,
  authorize,
  commit,
}) {
  const match = pathname.match(/^\/resorts\/([^/]+)\/class-pricing$/);
  if (!match) return { handled: false };
  const resortId = match[1];
  authorize(resortId);
  const resort = db.resorts.find((r) => r.id === resortId);
  if (!resort) fail("Санаторий не найден.", 404);
  const category = method === "GET" ? params.get("category") : payload.category;
  if (!["standard", "comfort", "suite"].includes(category))
    fail("Выберите класс номера.");
  const rooms = db.rooms
    .filter((r) => r.resortId === resortId && r.category === category)
    .sort(
      (a, b) => a.number.localeCompare(b.number) || a.id.localeCompare(b.id),
    );
  if (rooms.length > 2000)
    fail("В классе слишком много номеров для одной операции.", 409);
  if (method === "GET") {
    if ([...params.keys()].some((key) => key !== "category"))
      fail("Неизвестный параметр.");
    return {
      handled: true,
      value: {
        resortId,
        resortVersion: resort.version,
        category,
        roomCount: rooms.length,
        rooms: rooms.map(
          ({ id, number, title, status, version, pricePeriods = [] }) => ({
            id,
            number,
            title,
            status,
            version,
            pricePeriods: structuredClone(pricePeriods),
          }),
        ),
      },
    };
  }
  if (method !== "POST") fail("Операция недоступна.", 405);
  strict(payload, ["resortVersion", "category", "rooms", "period"]);
  strict(payload.period, ["label", "start", "end", "price"]);
  const periodError = validatePricePeriods([payload.period]);
  if (periodError) fail(periodError);
  if (
    !Array.isArray(payload.rooms) ||
    !payload.rooms.length ||
    payload.rooms.length > 2000
  )
    fail("Укажите номера выбранного класса.");
  for (const room of payload.rooms) strict(room, ["id", "version"]);
  const requested = new Map(
    payload.rooms.map((room) => [room.id, room.version]),
  );
  if (requested.size !== payload.rooms.length)
    fail("Номер указан несколько раз.");
  if (resort.status === "archived") fail("Санаторий в архиве.", 409);
  if (
    resort.version !== payload.resortVersion ||
    requested.size !== rooms.length ||
    rooms.some((room) => requested.get(room.id) !== room.version)
  )
    fail(
      "Состав класса или данные номеров изменились. Обновите список перед применением.",
      409,
    );
  const conflict = rooms.find(
    (room) =>
      (room.pricePeriods || []).length >= 60 ||
      (room.pricePeriods || []).some(
        (saved) =>
          saved.start < payload.period.end && payload.period.start < saved.end,
      ),
  );
  if (conflict)
    fail(
      `В номере № ${conflict.number} есть пересекающийся период. Ни один номер не изменён.`,
      409,
    );
  const before = {
    id: resortId,
    resortId,
    category,
    rooms: Object.fromEntries(rooms.map((r) => [r.id, r.version])),
  };
  const period = {
    ...payload.period,
    label: payload.period.label.trim(),
    price: Number(payload.period.price),
  };
  for (const room of rooms) {
    room.pricePeriods = [
      ...(room.pricePeriods || []),
      structuredClone(period),
    ].sort((a, b) => a.start.localeCompare(b.start));
    room.version++;
  }
  commit(
    "roomPricePeriods",
    {
      ...before,
      period,
      rooms: Object.fromEntries(rooms.map((r) => [r.id, r.version])),
    },
    before,
    "apply_to_class",
  );
  return {
    handled: true,
    value: { resortId, category, appliedCount: rooms.length },
  };
}
