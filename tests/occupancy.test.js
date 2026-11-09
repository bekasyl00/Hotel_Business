import test from "node:test";
import assert from "node:assert/strict";
import {
  calendarRows,
  occupancyState,
  shiftDay,
  propertyToday,
} from "../src/entities/booking/model/occupancy.js";
const rooms = [
  { id: "a", number: "102", title: "Comfort" },
  { id: "b", number: "20", title: "Suite" },
];
const b = (id, start, end, extra = {}) => ({
  id,
  roomId: "a",
  start,
  end,
  status: "confirmed",
  guestLabel: "Demo",
  ...extra,
});
test("colors follow actual stays, never infer check-in or departure from dates", () => {
  assert.equal(occupancyState(b("1", "2020-01-01", "2020-01-02")), "reserved");
  assert.equal(
    occupancyState(b("1", "", "", { checkedInAt: "2020-01-01" })),
    "active",
  );
  assert.equal(
    occupancyState(
      b("1", "", "", { checkedInAt: "2020-01-01", checkedOutAt: "2020-01-02" }),
    ),
    "past",
  );
  assert.equal(
    occupancyState(b("1", "", "", { status: "cancelled" })),
    "closed",
  );
  assert.equal(
    occupancyState(
      b("1", "", "", { status: "pending", holdExpiresAt: "2026-01-01" }),
      Date.parse("2026-01-01"),
    ),
    "closed",
  );
});
test("calendar clips across month boundaries and treats checkout as exclusive", () => {
  const rows = calendarRows(
    rooms,
    [
      b("1", "2026-01-28", "2026-02-02"),
      b("2", "2026-02-02", "2026-02-07"),
      b("3", "2026-01-29", "2026-01-30"),
      b("4", "2026-02-04", "2026-02-05"),
    ],
    "2026-01-30",
    5,
  );
  assert.equal(rows[0].room.number, "20");
  assert.deepEqual(
    rows[1].bars.map((x) => [x.from, x.span, x.lane]),
    [
      [0, 3, 0],
      [3, 2, 0],
    ],
  );
});
test("overlapping history uses separate lanes; search and states retain no foreign-room bookings", () => {
  const rows = calendarRows(
    rooms,
    [
      b("1", "2026-01-01", "2026-01-05"),
      b("2", "2026-01-02", "2026-01-04", { stayStatus: "checked_out" }),
      b("foreign", "2026-01-01", "2026-01-05", { roomId: "foreign" }),
    ],
    "2026-01-01",
    7,
    { query: "demo" },
  );
  assert.equal(rows.length, 1);
  assert.deepEqual(
    rows[0].bars.map((x) => x.lane),
    [0, 1],
  );
  assert.equal(
    calendarRows(rooms, [], "2026-01-01", 7, { state: "active" }).length,
    0,
  );
});
test("civil dates use property timezone and do not drift at month/year boundaries", () => {
  assert.equal(shiftDay("2026-12-31", 1), "2027-01-01");
  assert.equal(shiftDay("2024-03-01", -1), "2024-02-29");
  assert.equal(
    propertyToday("Asia/Almaty", new Date("2026-01-01T20:00:00Z")),
    "2026-01-02",
  );
});

test("property date remains ISO when a device Intl locale uses slash ordering", () => {
  const DateTimeFormat = Intl.DateTimeFormat;
  Intl.DateTimeFormat = function (_locale, options) {
    return new DateTimeFormat("en-US", options);
  };
  try {
    assert.equal(
      propertyToday("Asia/Almaty", new Date("2026-01-01T20:00:00Z")),
      "2026-01-02",
    );
    assert.equal(
      propertyToday("America/Los_Angeles", new Date("2026-01-01T02:00:00Z")),
      "2025-12-31",
    );
  } finally {
    Intl.DateTimeFormat = DateTimeFormat;
  }
});
