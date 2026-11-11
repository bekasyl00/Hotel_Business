import {
  propertyToday,
  shiftDay,
  roomPlaces,
  paymentTerms,
} from "../../entities/booking/rules.js";
import { ApiError } from "../../shared/api/index.js";

function resolveRoomBookingPlaces(room, roomBookings) {
  const activePlaces = roomPlaces(room).filter((p) => p.status === "active");
  const allIds = new Set(activePlaces.map((p) => p.id));
  const byPlace = new Map(activePlaces.map((p) => [p.id, []]));
  const sorted = [...roomBookings].sort((a, b) =>
    String(a.start).localeCompare(String(b.start)),
  );
  return sorted.map((b) => {
    let placeIds = Array.isArray(b.placeIds)
      ? b.placeIds.filter((id) => allIds.has(id))
      : [];
    if (!placeIds.length) {
      const needed = Math.max(
        1,
        Math.min(Number(b.guests) || 1, activePlaces.length),
      );
      const free = activePlaces.filter((p) =>
        (byPlace.get(p.id) || []).every(
          (other) => !(other.start < b.end && b.start < other.end),
        ),
      );
      const picked = free.slice(0, needed);
      if (picked.length < needed) {
        const used = new Set(picked.map((p) => p.id));
        for (const p of activePlaces) {
          if (!used.has(p.id)) {
            picked.push(p);
            if (picked.length === needed) break;
          }
        }
      }
      placeIds = picked.map((p) => p.id);
    }
    for (const pid of placeIds) {
      byPlace.get(pid)?.push(b);
    }
    return { booking: b, placeIds };
  });
}

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
  const activePlacesByRoom = new Map(
    rooms.map((r) => [
      r.id,
      roomPlaces(r).filter((p) => p.status === "active"),
    ]),
  );
  const allocationsByRoom = new Map(
    rooms.map((r) => [
      r.id,
      resolveRoomBookingPlaces(
        r,
        bookings.filter((b) => b.roomId === r.id),
      ),
    ]),
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
    const bookable =
      day >= today && day <= horizon && (day !== today || canArriveToday);
    const availableRoomsList = [];
    let availablePlaces = 0;
    if (bookable) {
      for (const room of rooms) {
        const totalActive = (activePlacesByRoom.get(room.id) || []).length;
        const busyIds = new Set();
        for (const item of allocationsByRoom.get(room.id) || []) {
          if (item.booking.start <= day && day < item.booking.end) {
            for (const pid of item.placeIds) busyIds.add(pid);
          }
        }
        const freeInRoom = Math.max(0, totalActive - busyIds.size);
        if (freeInRoom >= guests) {
          availableRoomsList.push(room);
          availablePlaces += freeInRoom;
        }
      }
    }
    const priceCandidates = bookable
      ? availableRoomsList
          .map((room) => {
            const period = (room.pricePeriods || []).find(
              (item) => item.start <= day && day < item.end,
            );
            return { room, period, price: period ? period.price : room.price };
          })
          .filter(
            ({ room, price }) =>
              Number.isSafeInteger(room.price) &&
              room.price >= 0 &&
              Number.isSafeInteger(price) &&
              price >= 0,
          )
          .sort(
            (a, b) =>
              a.price - b.price ||
              String(a.room.id).localeCompare(String(b.room.id)),
          )
      : [];
    const cheapest = priceCandidates[0];
    const inclusive = (amount) => paymentTerms(resort, amount)?.total ?? amount;
    let departureRooms = 0;
    let departurePlaces = 0;
    if (
      arrival &&
      day > arrival &&
      day <= shiftDay(arrival, 30) &&
      (arrival !== today || canArriveToday)
    ) {
      for (const room of rooms) {
        const totalActive = (activePlacesByRoom.get(room.id) || []).length;
        const blockedIds = new Set();
        for (const item of allocationsByRoom.get(room.id) || []) {
          if (item.booking.start < day && arrival < item.booking.end) {
            for (const pid of item.placeIds) blockedIds.add(pid);
          }
        }
        const continuousFree = Math.max(0, totalActive - blockedIds.size);
        if (continuousFree >= guests) {
          departureRooms += 1;
          departurePlaces += continuousFree;
        }
      }
    }
    days.push({
      date: day,
      availableRooms: availableRoomsList.length,
      availablePlaces,
      departureRooms,
      departurePlaces,
      bookable,
      price: cheapest ? inclusive(cheapest.price) : null,
      regularPrice: cheapest ? inclusive(cheapest.room.price) : null,
      priceKind: !cheapest
        ? null
        : cheapest.period
          ? cheapest.price < cheapest.room.price
            ? "discount"
            : "seasonal"
          : "regular",
      hasPricePeriod: !!cheapest?.period,
      periodLabel: cheapest?.period?.label || "",
    });
  }
  const totalPlaces = rooms.reduce(
    (sum, r) => sum + (activePlacesByRoom.get(r.id) || []).length,
    0,
  );
  return {
    month,
    today,
    timeZone,
    totalRooms: rooms.length,
    totalPlaces,
    days,
  };
}
