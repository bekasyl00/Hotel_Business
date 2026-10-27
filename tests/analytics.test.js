import test from "node:test";
import assert from "node:assert/strict";
import { demoAnalytics } from "../src/app/providers/demo-analytics.js";
import {
  createDemoTransport,
  DATABASE_KEY,
} from "../src/app/providers/demo.js";
import { dateAfter } from "../src/entities/booking/rules.js";

const admin = { role: "admin" };
const manager = { role: "manager", resortId: "a" };
const query = (values = {}) =>
  new URLSearchParams({ start: "2026-03-02", end: "2026-03-03", ...values });
function fixture() {
  return {
    resorts: [
      { id: "a", name: "А" },
      { id: "b", name: "Б" },
    ],
    rooms: [
      { id: "a1", resortId: "a", title: "Номер А", number: "101" },
      { id: "b1", resortId: "b", title: "Номер Б", number: "101" },
    ],
    bookings: [
      {
        id: "one",
        resortId: "a",
        roomId: "a1",
        total: 1000,
        status: "cancelled",
        createdAt: "2026-03-01T19:00:00Z",
        cancellation: { refundAmount: 700, createdAt: "2026-03-03T18:59:59Z" },
      },
      {
        id: "two",
        resortId: "b",
        roomId: "b1",
        total: 9000,
        status: "confirmed",
        createdAt: "2026-03-02T12:00:00Z",
      },
      {
        id: "old",
        resortId: "a",
        roomId: "a1",
        total: 500,
        status: "confirmed",
        createdAt: "2026-03-01T18:59:59Z",
      },
      {
        id: "later",
        resortId: "a",
        roomId: "a1",
        total: 800,
        status: "pending",
        createdAt: "2026-03-03T19:00:00Z",
      },
    ],
    payments: [
      {
        bookingId: "one",
        outcome: "success",
        amount: 1000,
        status: "partially_refunded",
        createdAt: "2026-03-01T18:59:59Z",
      },
      {
        bookingId: "one",
        outcome: "failed",
        amount: 1000,
        status: "failed",
        createdAt: "2026-03-02T10:00:00Z",
      },
      {
        bookingId: "two",
        outcome: "success",
        amount: 9000,
        createdAt: "2026-03-02T12:00:00Z",
      },
    ],
    reviews: [
      {
        bookingId: "old",
        resortId: "a",
        status: "approved",
        rating: 4,
        createdAt: "2026-03-02T12:00:00Z",
      },
      {
        bookingId: "old",
        resortId: "a",
        status: "pending",
        rating: 1,
        createdAt: "2026-03-02T12:00:00Z",
      },
    ],
  };
}
function memory() {
  const data = new Map();
  return {
    getItem: (k) => data.get(k) || null,
    setItem: (k, v) => data.set(k, v),
    removeItem: (k) => data.delete(k),
  };
}

test("analytics scope excludes foreign facts/options and refuses anonymous access", () => {
  const result = demoAnalytics(fixture(), manager, query());
  assert.deepEqual(result.resorts, [{ id: "a", name: "А" }]);
  assert.equal(result.byResort.length, 1);
  assert.equal(result.byRoom.length, 1);
  assert.equal(result.totals.bookingCount, 1);
  assert.equal(result.totals.bookedAmount, 1000);
  assert.throws(
    () => demoAnalytics(fixture(), null, query()),
    (e) => e.status === 401,
  );
  assert.throws(
    () => demoAnalytics(fixture(), manager, query({ resortId: "b" })),
    (e) => e.status === 403,
  );
  assert.throws(
    () => demoAnalytics(fixture(), admin, query({ resortId: "missing" })),
    (e) => e.status === 404,
  );
});

test("analytics counts event times at inclusive Almaty boundaries and permits negative net", () => {
  const result = demoAnalytics(fixture(), manager, query());
  assert.equal(result.totals.grossReceived, 0);
  assert.equal(result.totals.refunds, 700);
  assert.equal(result.totals.netReceived, -700);
  assert.equal(result.totals.statuses.cancelled, 1);
  assert.deepEqual(result.previousPeriod, {
    start: "2026-02-28",
    end: "2026-03-01",
  });
  assert.equal(result.previousTotals.bookingCount, 1);
  assert.equal(result.previousTotals.grossReceived, 1000);
  assert.equal(result.previousTotals.refunds, 0);
  assert.equal(result.totals.reviewCount, 2);
  assert.equal(result.totals.averageRating, 4);
  assert.equal(result.byRoom[0].reviewCount, 2);
  assert.equal(result.paymentMode, "demo");
});

test("daily zero buckets, Monday weeks and first-of-month groups preserve totals", () => {
  const db = fixture();
  const daily = demoAnalytics(db, manager, query({ end: "2026-03-05" }));
  assert.equal(daily.series.length, 4);
  assert.equal(daily.series.at(-1).bookingCount, 0);
  assert.equal(daily.series.at(-1).averageRating, null);
  const weekly = demoAnalytics(
    db,
    manager,
    query({ start: "2026-03-03", end: "2026-03-12", granularity: "week" }),
  );
  assert.deepEqual(
    weekly.series.map((r) => r.date),
    ["2026-03-02", "2026-03-09"],
  );
  assert.equal(
    weekly.series.reduce((sum, r) => sum + r.netReceived, 0),
    weekly.totals.netReceived,
  );
  const monthly = demoAnalytics(
    db,
    manager,
    query({ start: "2026-02-20", end: "2026-03-05", granularity: "month" }),
  );
  assert.deepEqual(
    monthly.series.map((r) => r.date),
    ["2026-02-01", "2026-03-01"],
  );
});

test("analytics validates dates/range/group and defaults to 28 Almaty days", () => {
  for (const values of [
    { start: "2026-02-30" },
    { start: "0001-01-01", end: "0001-01-02" },
    { start: "9999-01-01", end: "9999-01-02" },
    { start: "" },
    { start: "2026-03-04" },
    { start: "2024-01-01", end: "2025-01-01" },
    { granularity: "year" },
  ])
    assert.throws(
      () => demoAnalytics(fixture(), admin, query(values)),
      (e) => e.status === 422,
    );
  const result = demoAnalytics(
    fixture(),
    admin,
    new URLSearchParams(),
    Date.parse("2026-03-02T20:00:00Z"),
  );
  assert.equal(result.period.end, "2026-03-03");
  assert.equal(result.period.start, "2026-02-04");
  assert.equal(result.series.length, 28);
});

test("historical refund without event date is omitted and disclosed, never assigned booking date", () => {
  const db = fixture();
  delete db.bookings[0].cancellation.createdAt;
  const result = demoAnalytics(db, manager, query());
  assert.equal(result.totals.refunds, 0);
  assert.equal(result.refundDataIncomplete, true);
  assert.equal(result.previousTotals.refunds, 0);
});

test("analytics ranks all catalogue records, caps breakdowns and keeps full totals", () => {
  const db = fixture();
  for (let i = 0; i < 501; i++)
    db.rooms.push({
      id: `zero-${i}`,
      resortId: "a",
      title: "Пустой",
      number: `${i}`,
    });
  const result = demoAnalytics(db, admin, query());
  assert.equal(result.byResort[0].resortId, "b");
  assert.equal(result.byRoom[0].roomId, "b1");
  assert.equal(result.byRoom.length, 500);
  assert.equal(result.truncated.byRoom, true);
  assert.equal(result.totals.netReceived, 8300);
  assert.equal(result.totals.bookingCount, 2);
});

test("demo transport exposes scoped analytics and stamps actual cancellation event time", async () => {
  const storage = memory(),
    session = memory();
  const api = createDemoTransport({ storage, session, delay: 0 });
  await assert.rejects(api("GET", "/analytics"), (e) => e.status === 401);
  await api("POST", "/auth/login", { accountId: "admin" });
  const booking = await api("POST", "/bookings", {
    roomId: "altun-111",
    tariffId: "altun-meals",
    start: dateAfter(7),
    end: dateAfter(10),
    guests: 2,
    guestLabel: "Демо-гость",
  });
  const before = Date.now();
  const cancelled = await api("PATCH", `/bookings/${booking.id}`, {
    status: "cancelled",
    version: booking.version,
  });
  assert.ok(Date.parse(cancelled.cancellation.createdAt) >= before);
  assert.equal(
    JSON.parse(storage.getItem(DATABASE_KEY)).bookings[0].cancellation
      .createdAt,
    cancelled.cancellation.createdAt,
  );
  const analytics = await api("GET", "/analytics");
  assert.equal(analytics.totals.bookingCount, 1);
  assert.equal(analytics.totals.statuses.cancelled, 1);
  assert.equal(analytics.totals.refunds, 0);
});
