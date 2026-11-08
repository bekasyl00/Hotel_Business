import test from "node:test";
import assert from "node:assert/strict";
import { calendarDayPrice } from "../src/widgets/availability-calendar/model/price.js";

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
