import test from "node:test";
import assert from "node:assert/strict";
import {
  ageAt,
  birthHint,
  selectChildCount,
} from "../src/features/create-booking/model/children.js";
test("adding a child increases a one-person party while preserving an adult", () => {
  assert.deepEqual(selectChildCount("1", 1, 4), { children: 1, guests: 2 });
  assert.deepEqual(selectChildCount("2", 1, 4), { children: 2, guests: 3 });
  assert.deepEqual(selectChildCount("1", 4, 4), { children: 1, guests: 4 });
});
test("child count remains editable and cannot exceed room capacity with an adult", () => {
  assert.equal(selectChildCount("", 2, 4), null);
  assert.equal(selectChildCount("1.5", 2, 4), null);
  assert.equal(selectChildCount("invalid", 2, 4), null);
  assert.deepEqual(selectChildCount("9", 2, 4), { children: 3, guests: 4 });
  assert.deepEqual(selectChildCount("1", 1, 1), { children: 0, guests: 1 });
  assert.deepEqual(selectChildCount("0", 3, 4), { children: 0, guests: 3 });
});
test("child age uses arrival birthday, including leap dates", () => {
  assert.equal(ageAt("2024-11-09", "2027-11-08"), 2);
  assert.equal(ageAt("2024-11-09", "2027-11-09"), 3);
  assert.equal(ageAt("2024-02-29", "2027-02-28"), 2);
  assert.equal(ageAt("2024-02-29", "2027-03-01"), 3);
  assert.equal(ageAt("2023-02-29", "2027-03-01"), null);
  assert.equal(ageAt("2028-01-01", "2027-03-01"), null);
});
test("IIN prefix is a bounded demo date assumption, never an identity check", () => {
  assert.equal(birthHint("241109", "2026-11-08"), "2024-11-09");
  assert.equal(birthHint("241332", "2026-11-08"), "");
  assert.equal(birthHint("680406", "2026-11-08"), "");
  assert.equal(birthHint("241109123456", "2026-11-08"), "");
});

test("full 12-digit demo IIN yields only a child birth date, without a confirmation field", async () => {
  const { childBirthFromIin } =
    await import("../src/features/create-booking/model/children.js");
  assert.equal(
    childBirthFromIin("241109000000", "2026-11-15", "2026-11-08"),
    "2024-11-09",
  );
  for (const iin of [
    "241109",
    "2411090000000",
    "24110900000x",
    "２４１１０９００００００",
    "230229000000",
    "261109000000",
    "000101000000",
  ])
    assert.equal(childBirthFromIin(iin, "2026-11-15", "2026-11-08"), "");
  assert.equal(
    childBirthFromIin("240229000000", "2026-11-15", "2026-11-08"),
    "2024-02-29",
  );
});
