import test from "node:test";
import assert from "node:assert/strict";
import { paymentTerms } from "../src/entities/booking/model/payment-terms.js";

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
