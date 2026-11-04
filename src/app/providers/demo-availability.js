import { propertyToday, shiftDay } from "../../entities/booking/rules.js";
import { ApiError } from "../../shared/api/index.js";

export function demoAvailability(db, params, now = new Date()) {
  const fail = (status = 422) => {
    throw new ApiError("Invalid availability request", status);
  };
  if (
    [...params.keys()].some(
      (key) =>
        ![
          "resortId",
          "category",
          "roomId",
          "guests",
          "month",
          "arrival",
        ].includes(key),
    )
  )
    fail();
  const resort = db.resorts.find(
    (r) => r.id === params.get("resortId") && r.status === "published",
  );
  if (!resort) fail(404);
  const category = params.get("category"),
    month = params.get("month"),
    guests = Number(params.get("guests") ?? 1),
    roomId = params.get("roomId"),
    arrival = params.get("arrival"),
    timeZone = resort.timeZone || "Asia/Almaty",
    today = propertyToday(timeZone, now),
    horizon = shiftDay(today, 365);
  if (
    !["standard", "comfort", "suite"].includes(category) ||
    !/^\d{4}-(0[1-9]|1[0-2])$/.test(month) ||
    month < today.slice(0, 7) ||
    month > horizon.slice(0, 7) ||
    !Number.isInteger(guests) ||
    guests < 1 ||
    guests > 4
  )
    fail();
  if (
    arrival &&
    (!/^\d{4}-\d{2}-\d{2}$/.test(arrival) ||
      !Number.isFinite(Date.parse(arrival)) ||
      shiftDay(arrival, 0) !== arrival ||
      arrival < today ||
      arrival > horizon)
  )
    fail();
  const matching = db.rooms.filter(
    (r) =>
      r.resortId === resort.id &&
      r.category === category &&
      r.status === "active",
  );
  if (roomId && !matching.some((r) => r.id === roomId)) fail(404);
  const rooms = matching.filter(
    (r) => r.capacity >= guests && (!roomId || r.id === roomId),
  );
  const ids = new Set(rooms.map((r) => r.id));
  const bookings = db.bookings.filter(
    (b) =>
      ids.has(b.roomId) &&
      (b.status === "confirmed" ||
        (b.status === "pending" &&
          (!b.holdExpiresAt || Date.parse(b.holdExpiresAt) > now.getTime()))),
  );
  const localTime = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(now);
  const canArriveToday = localTime < (resort.checkInTime || "14:00");
  const days = [];
  for (
    let day = `${month}-01`;
    day.slice(0, 7) === month;
    day = shiftDay(day, 1)
  ) {
    const busy = new Set(
      bookings
        .filter((b) => b.start <= day && day < b.end)
        .map((b) => b.roomId),
    );
    const bookable =
      day >= today && day <= horizon && (day !== today || canArriveToday);
    let departureRooms = 0;
    if (
      arrival &&
      day > arrival &&
      day <= shiftDay(arrival, 30) &&
      (arrival !== today || canArriveToday)
    ) {
      const blocked = new Set(
        bookings
          .filter((b) => b.start < day && arrival < b.end)
          .map((b) => b.roomId),
      );
      departureRooms = rooms.length - blocked.size;
    }
    days.push({
      date: day,
      availableRooms: bookable ? rooms.length - busy.size : 0,
      departureRooms,
      bookable,
    });
  }
  return { month, today, timeZone, totalRooms: rooms.length, days };
}
