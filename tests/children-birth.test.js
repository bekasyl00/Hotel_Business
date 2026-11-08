import test from "node:test";
import assert from "node:assert/strict";
import {
  ageAt,
  birthHint,
  selectChildCount,
  roomForParty,
} from "../src/features/create-booking/model/children.js";
test("adding a child increases a one-person party while preserving an adult", () => {
  assert.deepEqual(selectChildCount("1", 1, 4), { children: 1, guests: 2 });
  assert.deepEqual(selectChildCount("2", 1, 4), { children: 2, guests: 3 });
  assert.deepEqual(selectChildCount("1", 4, 4), { children: 1, guests: 4 });
});
test("child count preserves requested two children independently from room capacity", () => {
  assert.equal(selectChildCount("", 2, 4), null);
  assert.equal(selectChildCount("1.5", 2, 4), null);
  assert.equal(selectChildCount("invalid", 2, 4), null);
  assert.equal(selectChildCount("9", 2, 4), null);
  assert.equal(selectChildCount("1", 1, 1), null);
  assert.deepEqual(selectChildCount("2", 2), { children: 2, guests: 3 });
  assert.deepEqual(selectChildCount("3", 2), { children: 3, guests: 4 });
  assert.deepEqual(selectChildCount("0", 3, 4), { children: 0, guests: 3 });
});
test("larger room is selected without silently dropping children or changing the current class unnecessarily", () => {
  const small = {
    id: "small",
    status: "active",
    category: "standard",
    capacity: 2,
  };
  const large = {
    id: "large",
    status: "active",
    category: "standard",
    capacity: 4,
  };
  const premium = {
    id: "premium",
    status: "active",
    category: "premium",
    capacity: 3,
  };
  const rooms = [small, premium, large];
  assert.equal(roomForParty(rooms, "small", 2), small);
  assert.equal(roomForParty(rooms, "small", 3), large);
  assert.equal(roomForParty([small, premium], "small", 3), premium);
  assert.equal(roomForParty([small], "small", 3), null);
  assert.equal(
    roomForParty([small, { ...large, status: "maintenance" }], "small", 3),
    null,
  );
  assert.equal(small.capacity, 2);
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
  assert.equal(birthHint("121109", "2026-11-08"), "2012-11-09");
  assert.equal(birthHint("121109", "2026-11-09"), "");
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
