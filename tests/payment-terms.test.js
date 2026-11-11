import test from "node:test";
import assert from "node:assert/strict";
import {
  paymentTerms,
  customerPrice,
  customerQuote,
  customerNightPrice,
} from "../src/entities/booking/model/payment-terms.js";
import { quoteStay } from "../src/entities/booking/model/rules.js";

test("online commission is added to accommodation, which remains payable at the property", () => {
  const expected = {
    version: 1,
    accommodationTotal: 10000,
    onlineAmount: 1000,
    onsiteAmount: 10000,
    total: 11000,
    mode: "percent",
    value: "10",
  };
  assert.deepEqual(
    paymentTerms({ bookingFeePercent: "10.00" }, 10000),
    expected,
  );
  assert.deepEqual(
    paymentTerms({ commissionPercent: "10.00" }, 10000),
    expected,
  );
  assert.equal(
    paymentTerms({ bookingFeePercent: "10", commissionPercent: "90" }, 10000)
      .onlineAmount,
    1000,
  );
  assert.equal(paymentTerms({ bookingFeePercent: "100" }, 10000).total, 20000);
});

test("commission rounds half up to whole tenge, including two-decimal percentages", () => {
  for (const [total, percent, fee] of [
    [10004, "10", 1000],
    [10005, "10", 1001],
    [10039, "1.25", 125],
    [10040, "1.25", 126],
    [1, "50", 1],
  ]) {
    const terms = paymentTerms({ bookingFeePercent: percent }, total);
    assert.equal(terms.onlineAmount, fee);
    assert.equal(terms.total, total + fee);
    assert.equal(terms.onsiteAmount, total);
  }
  assert.equal(paymentTerms({ bookingFeePercent: "49.99" }, 1), null);
});

test("an unset, zero or invalid fee never invents an online payment amount", () => {
  for (const percent of [
    undefined,
    null,
    "",
    0,
    "0.00",
    -1,
    "100.01",
    "unknown",
    Infinity,
  ]) {
    assert.equal(paymentTerms({ bookingFeePercent: percent }, 10000), null);
  }
  for (const total of [
    -1,
    0,
    0.5,
    "10000",
    NaN,
    Infinity,
    Number.MAX_SAFE_INTEGER + 1,
  ]) {
    assert.equal(paymentTerms({ bookingFeePercent: "10" }, total), null);
  }
});

test("an already computed fee does not change when the resort's fee is edited", () => {
  const resort = { bookingFeePercent: "10" };
  const first = paymentTerms(resort, 10000);
  resort.bookingFeePercent = "20";
  const second = paymentTerms(resort, 10000);
  assert.equal(first.onlineAmount, 1000);
  assert.equal(first.total, 11000);
  assert.equal(first.value, "10");
  assert.equal(second.onlineAmount, 2000);
});

test("public price estimates include the configured amount and sort by the payable price", () => {
  assert.equal(customerPrice({ bookingFeePercent: "10" }, 10000), 11000);
  const cards = [
    { id: "first", bookingFeePercent: "20", price: 10000 },
    { id: "second", bookingFeePercent: "5", price: 11000 },
  ]
    .map((resort) => ({
      id: resort.id,
      price: customerPrice(resort, resort.price),
    }))
    .sort((a, b) => a.price - b.price);
  assert.deepEqual(cards, [
    { id: "second", price: 11550 },
    { id: "first", price: 12000 },
  ]);
  for (const bookingFeePercent of [null, 0, undefined]) {
    assert.equal(customerPrice({ bookingFeePercent }, 10000), 10000);
    assert.equal(paymentTerms({ bookingFeePercent }, 10000), null);
  }
  for (const value of [NaN, -1, 12.5, "10000"]) {
    assert.equal(customerPrice({ bookingFeePercent: "10" }, value), null);
  }
});

test("public nightly breakdown reconciles to the once-rounded stay total", () => {
  const base = quoteStay({ price: 10005 }, null, {
    start: "2027-01-01",
    end: "2027-01-03",
    guests: 1,
  });
  const snapshot = structuredClone(base);
  const display = customerQuote({ bookingFeePercent: "10" }, base);
  assert.equal(base.total, 20010);
  assert.equal(display.total, 22011);
  assert.equal(
    display.total,
    paymentTerms({ bookingFeePercent: "10" }, base.total).total,
  );
  assert.deepEqual(
    display.nightlyBreakdown.map((line) => line.nightly),
    [11006, 11005],
  );
  assert.equal(display.nightly, null);
  assert.equal(display.averageNightly, 11006);
  assert.equal(
    display.nightlyBreakdown.reduce((sum, line) => sum + line.nightly, 0),
    display.total,
  );
  assert.deepEqual(base, snapshot);
});

test("seasonal and discounted guest quotes keep accommodation snapshots unchanged", () => {
  const room = {
    price: 10000,
    pricePeriods: [
      { start: "2027-01-02", end: "2027-01-03", price: 15000, label: "Winter" },
    ],
  };
  const tariff = {
    supplement: 1000,
    priceKind: "discount",
    discountPercent: 10,
  };
  const quote = quoteStay(room, tariff, {
    start: "2027-01-01",
    end: "2027-01-04",
    guests: 2,
  });
  const snapshot = structuredClone(quote);
  const display = customerQuote({ bookingFeePercent: "10" }, quote);
  assert.equal(quote.total, 68400);
  assert.equal(display.total, 75240);
  assert.equal(display.regularTotal, 83600);
  assert.equal(display.nightly, null);
  assert.equal(display.regularNightly, null);
  assert.deepEqual(
    display.nightlyBreakdown.map((line) => line.nightly),
    [21780, 31680, 21780],
  );
  assert.equal(display.nightlyBreakdown[1].periodLabel, "Winter");
  assert.deepEqual(quote, snapshot);
  assert.equal(room.price, 10000);
  assert.equal(room.pricePeriods[0].price, 15000);
  assert.equal(
    customerQuote({ bookingFeePercent: null }, quote).total,
    quote.total,
  );
});

test("uniform guest estimates stay uniform and invalid quotes have no displayed total", () => {
  const quote = quoteStay({ price: 10000 }, null, {
    start: "2027-01-01",
    end: "2027-01-03",
    guests: 1,
  });
  const display = customerQuote({ bookingFeePercent: "10" }, quote);
  assert.equal(display.nightly, 11000);
  assert.equal(display.total, 22000);
  assert.equal(customerQuote({}, null), null);
  assert.equal(customerQuote({}, { nightlyBreakdown: [] }), null);
  assert.equal(
    customerQuote(
      {},
      { nightlyBreakdown: [{ nightly: NaN, regularNightly: 10 }] },
    ),
    null,
  );
});

test("arrival prices show lower periods as a reduction and higher periods as seasonal", () => {
  const resort = { bookingFeePercent: "10" };
  const room = {
    price: 10000,
    pricePeriods: [
      { start: "2027-01-02", end: "2027-01-03", price: 15000, label: "Peak" },
      { start: "2027-01-03", end: "2027-01-04", price: 8000, label: "Quiet" },
    ],
  };
  const base = structuredClone(room);
  assert.deepEqual(
    customerNightPrice(resort, room, null, { start: "2027-01-01", guests: 1 }),
    { date: "2027-01-01", price: 11000, regularPrice: 11000, kind: "regular" },
  );
  assert.deepEqual(
    customerNightPrice(resort, room, null, { start: "2027-01-02", guests: 1 }),
    { date: "2027-01-02", price: 16500, regularPrice: 11000, kind: "seasonal" },
  );
  assert.deepEqual(
    customerNightPrice(resort, room, null, { start: "2027-01-03", guests: 1 }),
    { date: "2027-01-03", price: 8800, regularPrice: 11000, kind: "discount" },
  );
  assert.deepEqual(room, base);
  assert.equal(
    customerNightPrice(resort, room, null, { start: "invalid", guests: 1 }),
    null,
  );
});

test("arrival price honors rate supplements and does not mislabel a price increase as a discount", () => {
  const resort = { bookingFeePercent: "10" };
  const room = {
    price: 10000,
    pricePeriods: [{ start: "2027-01-02", end: "2027-01-03", price: 15000 }],
  };
  const tariff = {
    supplement: 1000,
    priceKind: "discount",
    discountPercent: 10,
  };
  const current = customerNightPrice(resort, room, tariff, {
    start: "2027-01-02",
    guests: 2,
  });
  assert.equal(current.price, 31680);
  assert.equal(current.regularPrice, 24200);
  assert.equal(current.kind, "seasonal");
  assert.equal(
    customerNightPrice(resort, room, tariff, { start: "2027-01-03", guests: 2 })
      .kind,
    "discount",
  );
});
