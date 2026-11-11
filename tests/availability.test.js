import test from "node:test";
import assert from "node:assert/strict";
import { demoAvailability } from "../src/app/providers/demo-availability.js";
import { createDemoTransport } from "../src/app/providers/demo.js";
import { dateAfter } from "../src/entities/booking/rules.js";

const now = new Date("2027-01-10T00:00:00Z");
function setup() {
  const db = {
    resorts: [
      {
        id: "resort",
        status: "published",
        timeZone: "Asia/Almaty",
        checkInTime: "14:00",
        commissionPercent: "10",
      },
    ],
    rooms: [
      {
        id: "a",
        resortId: "resort",
        category: "standard",
        capacity: 2,
        status: "active",
        price: 18000,
      },
    ],
    bookings: [],
  };
  const get = (extra = {}) =>
    demoAvailability(
      db,
      new URLSearchParams({
        resortId: "resort",
        category: "standard",
        guests: 2,
        month: "2027-01",
        ...extra,
      }),
      now,
    );
  const reserve = (roomId, start = 12, end = 14, extra = {}) =>
    db.bookings.push({
      roomId,
      start: `2027-01-${start}`,
      end: `2027-01-${end}`,
      status: "confirmed",
      ...extra,
    });
  return { db, get, reserve };
}
const day = (result, day) => result.days[day - 1];

test("calendar scopes class, capacity and publication without PII", () => {
  const { db, get, reserve } = setup();
  reserve("a");
  for (const [id, category, capacity, status] of [
    ["b", "comfort", 2, "active"],
    ["c", "standard", 1, "active"],
    ["d", "standard", 2, "maintenance"],
  ])
    db.rooms.push({ ...db.rooms[0], id, category, capacity, status });
  assert.equal(get().totalRooms, 1);
  assert.equal(day(get(), 12).availableRooms, 0);
  assert.equal(day(get({ category: "comfort" }), 12).availableRooms, 1);
  assert.throws(
    () => get({ roomId: "b" }),
    (e) => e.status === 404,
  );
  assert.deepEqual(
    Object.keys(day(get(), 12)).sort(),
    [
      "date",
      "availableRooms",
      "availablePlaces",
      "departureRooms",
      "departurePlaces",
      "bookable",
      "price",
      "regularPrice",
      "priceKind",
      "hasPricePeriod",
      "periodLabel",
    ].sort(),
  );
  db.resorts[0].status = "draft";
  assert.throws(
    () => get(),
    (e) => e.status === 404,
  );
});

test("calendar prices use the cheapest available room and that same room's baseline", () => {
  const { db, get, reserve } = setup();
  db.rooms[0].pricePeriods = [
    { start: "2027-01-11", end: "2027-01-16", price: 16000, label: "Winter" },
  ];
  db.rooms.push({
    ...db.rooms[0],
    id: "b",
    price: 30000,
    pricePeriods: [
      { start: "2027-01-12", end: "2027-01-14", price: 22000, label: "Offer" },
    ],
  });
  reserve("a", 12, 14);
  let current = day(get(), 12);
  assert.equal(current.availableRooms, 1);
  assert.equal(current.price, 24200);
  assert.equal(current.regularPrice, 33000);
  assert.equal(current.priceKind, "discount");
  assert.equal(current.hasPricePeriod, true);
  assert.equal(current.periodLabel, "Offer");
  current = day(get(), 14);
  assert.equal(current.price, 17600);
  assert.equal(current.regularPrice, 19800);
  assert.equal(current.periodLabel, "Winter");
  current = day(get({ roomId: "b" }), 14);
  assert.equal(current.price, 33000);
  assert.equal(current.priceKind, "regular");
  assert.equal(current.hasPricePeriod, false);
  assert.equal(current.periodLabel, "");
});

test("seasonal increases are not discounts; busy, past and departure-only cells have no nightly price", () => {
  const { db, get, reserve } = setup();
  db.rooms[0].pricePeriods = [
    { start: "2027-01-11", end: "2027-01-13", price: 20000, label: "Peak" },
  ];
  assert.equal(day(get(), 11).price, 22000);
  assert.equal(day(get(), 11).priceKind, "seasonal");
  db.rooms[0].pricePeriods[0].price = 18000;
  assert.equal(day(get(), 11).priceKind, "seasonal");
  reserve("a", 12, 14);
  const result = get({ arrival: "2027-01-11" });
  assert.equal(day(result, 12).departureRooms, 1);
  for (const current of [day(result, 9), day(result, 12), day(result, 13)]) {
    assert.equal(current.price, null);
    assert.equal(current.regularPrice, null);
    assert.equal(current.hasPricePeriod, false);
    assert.equal(current.priceKind, null);
  }
});

test("calendar uses active holds and exclusive checkout", () => {
  const { get, reserve } = setup();
  reserve("a", 12, 14, {
    status: "pending",
    holdExpiresAt: "2027-01-10T00:10:00Z",
  });
  reserve("a", 14, 15, {
    status: "pending",
    holdExpiresAt: "2027-01-09T00:00:00Z",
  });
  reserve("a", 15, 16, { status: "cancelled" });
  reserve("a", 16, 17, { status: "pending" });
  assert.deepEqual(
    [12, 13, 14, 15, 16].map((d) => day(get(), d).availableRooms),
    [0, 0, 1, 1, 0],
  );
});

test("green nights in different rooms do not imply a continuous available stay", () => {
  const { db, get, reserve } = setup();
  db.rooms.push({ ...db.rooms[0], id: "b" });
  reserve("a", 12, 13);
  reserve("b", 11, 12);
  const result = get({ arrival: "2027-01-11" });
  assert.equal(day(result, 11).availableRooms, 1);
  assert.equal(day(result, 12).availableRooms, 1);
  assert.equal(day(result, 12).departureRooms, 1);
  assert.equal(day(result, 13).departureRooms, 0);
  const exact = get({ roomId: "a", arrival: "2027-01-11" });
  assert.equal(exact.totalRooms, 1);
  assert.equal(day(exact, 12).availableRooms, 0);
  assert.equal(day(exact, 12).departureRooms, 1);
});

test("calendar bounds invalid inputs, past dates and property check-in cutoff", () => {
  const { db, get } = setup();
  for (const extra of [
    { month: "0000-01" },
    { month: "2027-13" },
    { month: "2099-01" },
    { month: "2026-12" },
    { category: "all" },
    { guests: 0 },
    { arrival: "2027-02-30" },
    { arrival: "2026-01-01" },
  ])
    assert.throws(
      () => get(extra),
      (e) => e.status === 422,
    );
  assert.equal(day(get(), 9).bookable, false);
  assert.equal(day(get(), 10).availableRooms, 1);
  db.resorts[0].checkInTime = "04:00";
  assert.equal(day(get(), 10).bookable, false);
  assert.equal(day(get({ arrival: "2027-01-10" }), 11).departureRooms, 0);
});

test("departure checking spans month boundaries and enforces 30 nights", () => {
  const { get, reserve } = setup();
  assert.equal(
    day(get({ month: "2027-02", arrival: "2027-01-10" }), 10).departureRooms,
    0,
  );
  reserve("a", 30, 31);
  const result = get({ month: "2027-02", arrival: "2027-01-29" });
  assert.equal(result.days.length, 28);
  assert.equal(day(result, 1).availableRooms, 1);
  assert.equal(day(result, 1).departureRooms, 0);
});

test("demo transport exposes the same bounded public calendar contract", async () => {
  const memory = () => {
    const values = new Map();
    return {
      getItem: (k) => values.get(k) || null,
      setItem: (k, v) => values.set(k, v),
      removeItem: (k) => values.delete(k),
    };
  };
  const api = createDemoTransport({
    storage: memory(),
    session: memory(),
    delay: 0,
  });
  const catalog = await api("GET", "/catalog");
  const room = catalog.rooms[0];
  const result = await api(
    "GET",
    `/availability-calendar?${new URLSearchParams({
      resortId: room.resortId,
      category: room.category,
      month: dateAfter(7).slice(0, 7),
      guests: 1,
    })}`,
  );
  assert.equal(
    result.totalRooms,
    catalog.rooms.filter(
      (r) =>
        r.resortId === room.resortId &&
        r.category === room.category &&
        r.status === "active",
    ).length,
  );
  assert.ok(result.days.length >= 28 && result.days.length <= 31);
});
