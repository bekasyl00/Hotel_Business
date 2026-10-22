import test from "node:test";
import assert from "node:assert/strict";
import {
  availableUnits,
  overlaps,
  quote,
  reserve,
  validateSearch,
  dateAfter,
  nightsBetween,
} from "../src/domain.js";
import { resorts, tariffs } from "../src/data.js";
const search = { start: dateAfter(7), end: dateAfter(10), guests: 2 };
const resort = resorts[0],
  room = resort.rooms[0];
test("checkout day can be reused; genuine overlap cannot", () => {
  assert.equal(
    overlaps(
      { start: "2027-01-01", end: "2027-01-03" },
      { start: "2027-01-03", end: "2027-01-05" },
    ),
    false,
  );
  assert.equal(
    overlaps(
      { start: "2027-01-01", end: "2027-01-04" },
      { start: "2027-01-03", end: "2027-01-05" },
    ),
    true,
  );
});
test("reject invalid, past, zero-night, long and impossible dates", () => {
  assert.equal(validateSearch(search), "");
  for (const change of [
    { start: dateAfter(-1) },
    { end: search.start },
    { end: dateAfter(40) },
    { start: "2027-02-30" },
    { guests: 5 },
    { start: "" },
  ])
    assert.ok(validateSearch({ ...search, ...change }));
});
test("price is per room; supplements are per guest per night", () => {
  assert.deepEqual(quote(room, tariffs[1], search), {
    nights: 3,
    nightly: 33000,
    total: 99000,
  });
  assert.equal(nightsBetween("2027-03-27", "2027-03-30"), 3);
});
test("allocation exhausts inventory and cancellation releases it", () => {
  const first = reserve({
    resort,
    room,
    tariff: tariffs[0],
    search,
    reservations: [],
  });
  const second = reserve({
    resort,
    room,
    tariff: tariffs[0],
    search,
    reservations: [first],
  });
  assert.notEqual(first.unit, second.unit);
  assert.throws(
    () =>
      reserve({
        resort,
        room,
        tariff: tariffs[0],
        search,
        reservations: [first, second],
      }),
    /занят/,
  );
  assert.deepEqual(
    availableUnits(room, search, [{ ...first, status: "cancelled" }, second]),
    [first.unit],
  );
});
test("rooms cannot exceed guest capacity", () =>
  assert.deepEqual(availableUnits(room, { ...search, guests: 3 }, []), []));
