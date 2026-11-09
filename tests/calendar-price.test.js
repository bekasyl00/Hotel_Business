import test from "node:test";
import assert from "node:assert/strict";
import {
  calendarDayPrice,
  compactCalendarPrice,
} from "../src/widgets/availability-calendar/model/price.js";

const day = {
  bookable: true,
  availableRooms: 1,
  price: 19800,
  regularPrice: 22000,
  hasPricePeriod: true,
  periodLabel: "Winter",
};
test("calendar never presents a busy or checkout-only night as chargeable", () => {
  for (const change of [
    { bookable: false },
    { availableRooms: 0, departureRooms: 2 },
    { price: null },
    { price: -1 },
    { price: Infinity },
  ])
    assert.equal(calendarDayPrice({ ...day, ...change }), null);
  assert.equal(calendarDayPrice(day).amount, 19800);
});
test("price markers and old-price comparison follow actual lower versus seasonal amounts", () => {
  assert.equal(calendarDayPrice(day).kind, "discount");
  assert.equal(
    calendarDayPrice({ ...day, price: 30000, priceKind: "discount" }).kind,
    "seasonal",
  );
  assert.equal(calendarDayPrice({ ...day, price: 22000 }).kind, "seasonal");
  assert.equal(
    calendarDayPrice({ ...day, hasPricePeriod: false }).kind,
    "regular",
  );
  assert.equal(
    calendarDayPrice({ ...day, price: 1100000, regularPrice: 1000000 }).amount,
    1100000,
  );
});

test("narrow calendars use short labels while retaining exact amounts for quotes and accessibility", () => {
  for (const [amount, expected] of [
    [0, "0"],
    [999, "999"],
    [1000, "1K"],
    [26400, "26.4K"],
    [26401, "26.4K"],
    [999950, "1M"],
    [1100000, "1.1M"],
  ]) {
    assert.equal(compactCalendarPrice(amount, "en"), expected);
    const price = calendarDayPrice({ ...day, price: amount });
    assert.equal(price.amount, amount);
  }
  assert.equal(compactCalendarPrice(26400, "ru"), "26,4K");
  assert.equal(compactCalendarPrice(26400, "kk"), "26,4K");
  for (const invalid of [null, undefined, -1, 1.1, Infinity, NaN])
    assert.equal(compactCalendarPrice(invalid, "en"), "");
});
