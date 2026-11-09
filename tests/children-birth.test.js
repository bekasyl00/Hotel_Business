import test from "node:test";
import assert from "node:assert/strict";
import {
  ageAt,
  birthHint,
  partySize,
  childDatePreview,
  monthsAt,
  roomForParty,
} from "../src/features/create-booking/model/children.js";
test("children add to older guests and cannot silently replace them", () => {
  assert.equal(partySize(2, 0), 2);
  assert.equal(partySize(2, 1), 3);
  assert.equal(partySize(2, 2), 4);
  assert.equal(partySize(1, 3), 4);
  assert.equal(partySize(2, 3), null);
  assert.equal(partySize(0, 1), null);
  assert.equal(partySize("", 1), null);
  assert.equal(partySize("1.5", 1), null);
});

test("date preview appears after six digits while complete IIN remains required", () => {
  const preview = childDatePreview("251212", "2026-11-17", "2026-11-10");
  assert.deepEqual(preview, {
    status: "incomplete",
    birth: "2025-12-12",
    age: 0,
    months: 11,
  });
  assert.equal(
    childDatePreview("251212000000", "2026-11-17", "2026-11-10").status,
    "ready",
  );
  assert.equal(monthsAt("2025-12-12", "2026-11-11"), 10);
  assert.equal(monthsAt("2025-12-12", "2026-11-12"), 11);
  assert.equal(monthsAt("2026-11-10", "2026-11-10"), 0);
});

test("prefix validation distinguishes invalid dates, future births and age 14 at arrival", () => {
  for (const prefix of ["230229", "241331", "240000"])
    assert.equal(
      childDatePreview(prefix, "2026-11-17", "2026-11-10").status,
      "invalidBirthDate",
    );
  assert.equal(
    childDatePreview("261111", "2026-11-17", "2026-11-10").status,
    "futureBirthDate",
  );
  assert.equal(
    childDatePreview("121117", "2026-11-17", "2026-11-10").status,
    "overChildAge",
  );
  assert.equal(childDatePreview("121118", "2026-11-17", "2026-11-10").age, 13);
  assert.equal(
    childDatePreview("24110900000x", "2026-11-17", "2026-11-10").status,
    "invalidIin",
  );
  assert.equal(
    childDatePreview("241109", "", "2026-11-10").status,
    "arrivalRequired",
  );
});

test("leading zero and century rollover dates preserve YYMMDD meaning", () => {
  assert.equal(
    childDatePreview("000229000000", "2001-03-01", "2001-02-28").birth,
    "2000-02-29",
  );
  assert.equal(
    childDatePreview("991201000000", "2101-03-01", "2101-02-28").birth,
    "2099-12-01",
  );
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
