import test from "node:test";
import assert from "node:assert/strict";
import {
  quoteStay,
  validateChildren,
  validatePricePeriods,
} from "../src/entities/booking/model/rules.js";
const room = {
  price: 10001,
  pricePeriods: [
    { label: "Season", start: "2027-02-01", end: "2027-02-03", price: 20001 },
  ],
};
const tariff = {
  supplement: 101,
  priceKind: "discount",
  discountPercent: 10,
  childrenUnderTwoFree: true,
};
const search = {
  start: "2027-01-31",
  end: "2027-02-04",
  guests: 2,
  childrenAges: [1],
};
test("nightly seasonal and child quote matches server contract across month boundaries", () => {
  const result = quoteStay(room, tariff, search);
  assert.equal(result.total, 54368);
  assert.equal(result.nightly, null);
  assert.deepEqual(
    result.nightlyBreakdown.map((p) => p.nightly),
    [9092, 18092, 18092, 9092],
  );
  assert.equal(result.chargeableGuests, 1);
  assert.equal(result.freeChildren, 1);
  room.pricePeriods[0].price = 30001;
  assert.equal(result.total, 54368);
  room.pricePeriods[0].price = 20001;
});
test("free child tariff is opt-in and ends at age two; room always payable", () => {
  for (const [t, s] of [
    [{ ...tariff, childrenUnderTwoFree: false }, search],
    [tariff, { ...search, childrenAges: [2] }],
    [tariff, { ...search, childrenAges: [] }],
  ]) {
    assert.equal(quoteStay(room, t, s).total, 54732);
  }
  assert.equal(
    quoteStay(
      { price: 18000 },
      { supplement: 4500, childrenUnderTwoFree: true },
      { ...search, start: "2027-01-01", end: "2027-01-02" },
    ).total,
    22500,
  );
});
test("only ages zero and one get the configured exemption; older children remain paying guests", () => {
  for (const [age, total, freeChildren] of [
    [0, 11000, 1],
    [1, 11000, 1],
    [2, 12000, 0],
    [13, 12000, 0],
  ]) {
    const result = quoteStay(
      { price: 10000 },
      { supplement: 1000, childrenUnderTwoFree: true },
      {
        start: "2027-01-01",
        end: "2027-01-02",
        guests: 2,
        childrenAges: [age],
      },
    );
    assert.equal(result.total, total);
    assert.equal(result.freeChildren, freeChildren);
    assert.equal(result.pricingVersion, 3);
    assert.equal(result.childrenUnderTwoFree, true);
    assert.equal(result.childrenUnderThreeFree, undefined);
  }
  const oldSnapshot = {
    pricingVersion: 2,
    total: 11000,
    childrenAges: [2],
    childrenUnderThreeFree: true,
    freeChildren: 1,
  };
  const before = structuredClone(oldSnapshot);
  const result = quoteStay(
    { price: 10000 },
    { supplement: 1000, childrenUnderThreeFree: true },
    { start: "2027-01-01", end: "2027-01-02", guests: 2, childrenAges: [2] },
  );
  assert.equal(result.total, 12000);
  assert.deepEqual(oldSnapshot, before);
});
test("period validation accepts adjoining dates and rejects overlap, invalid dates or prices", () => {
  assert.equal(
    validatePricePeriods([
      ...room.pricePeriods,
      { label: "Next", start: "2027-02-03", end: "2027-03-01", price: 0 },
    ]),
    "",
  );
  assert.ok(validatePricePeriods([...room.pricePeriods, ...room.pricePeriods]));
  assert.ok(
    validatePricePeriods([
      { label: "x", start: "2027-02-30", end: "2027-03-01", price: 1 },
    ]),
  );
  assert.ok(validatePricePeriods([{ ...room.pricePeriods[0], price: -1 }]));
  assert.ok(validatePricePeriods(Array(61).fill(room.pricePeriods[0])));
});
test("child composition requires an adult and complete integer ages", () => {
  for (const ages of [[null], [-1], [14], [18], [0, 0], ["2"]])
    assert.ok(validateChildren(2, ages));
  assert.equal(validateChildren(2, [0]), "");
  assert.equal(
    quoteStay(room, tariff, { ...search, childrenAges: [null] }),
    null,
  );
  for (const guests of [0, -1, 5, "", 1.5])
    assert.equal(quoteStay(room, tariff, { ...search, guests }), null);
});
