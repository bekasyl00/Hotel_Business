import test from "node:test";
import assert from "node:assert/strict";
import {
  ageAt,
  birthHint,
} from "../src/features/create-booking/model/children.js";
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
