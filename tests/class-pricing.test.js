import test from "node:test";
import assert from "node:assert/strict";
import { createDemoTransport } from "../src/app/providers/demo.js";
import {
  classPricingConflicts,
  classPricingPayload,
} from "../src/features/class-pricing/model/period.js";

function memory() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}
async function setup() {
  const api = createDemoTransport({
    storage: memory(),
    session: memory(),
    delay: 0,
  });
  await api("POST", "/auth/login", { accountId: "admin" });
  const preview = await api(
    "GET",
    "/resorts/altun/class-pricing?category=standard",
  );
  return { api, preview };
}
const period = {
  label: "Winter",
  start: "2027-01-12",
  end: "2027-01-14",
  price: "12345",
};

test("class seasonal form submits exact versioned scope and rejects incomplete price/date", () => {
  const preview = {
    resortVersion: 3,
    category: "standard",
    rooms: [{ id: "room-1", version: 2 }],
  };
  assert.deepEqual(classPricingPayload(preview, period), {
    resortVersion: 3,
    category: "standard",
    rooms: [{ id: "room-1", version: 2 }],
    period: { ...period, price: 12345 },
  });
  for (const value of [
    { price: "" },
    { price: -1 },
    { price: 1.5 },
    { price: 10000001 },
    { end: period.start },
    { label: " " },
  ])
    assert.equal(classPricingPayload(preview, { ...period, ...value }), null);
  assert.equal(classPricingPayload({ ...preview, rooms: [] }, period), null);
  assert.equal(
    classPricingPayload(preview, { ...period, price: 0 }).period.price,
    0,
  );
});

test("class overlap preview respects exclusive checkout boundary", () => {
  const rooms = [
    {
      id: "adjacent",
      pricePeriods: [{ ...period, start: "2027-01-10", end: "2027-01-12" }],
    },
    {
      id: "overlap",
      pricePeriods: [{ ...period, start: "2027-01-13", end: "2027-01-15" }],
    },
    {
      id: "limit",
      pricePeriods: Array.from({ length: 60 }, () => ({
        start: "2025-01-01",
        end: "2025-01-02",
      })),
    },
  ];
  assert.deepEqual(
    classPricingConflicts(rooms, period).map((room) => room.id),
    ["overlap", "limit"],
  );
});

test("demo applies seasonal price to all selected class rooms in one audit and preserves other classes", async () => {
  const { api, preview } = await setup();
  assert.ok(preview.roomCount > 1);
  const before = await api("GET", "/workspace");
  const payload = classPricingPayload(preview, period);
  const result = await api("POST", "/resorts/altun/class-pricing", payload);
  assert.equal(result.appliedCount, preview.roomCount);
  const after = await api("GET", "/workspace");
  for (const room of after.rooms) {
    const original = before.rooms.find((r) => r.id === room.id);
    if (payload.rooms.some((r) => r.id === room.id)) {
      assert.equal(room.version, original.version + 1);
      assert.deepEqual(room.pricePeriods.at(-1), { ...period, price: 12345 });
    } else assert.deepEqual(room, original);
  }
  assert.equal(after.audit.length, before.audit.length + 1);
  assert.equal(after.audit[0].action, "apply_to_class");
  await assert.rejects(
    api("POST", "/resorts/altun/class-pricing", payload),
    (error) => error.status === 409,
  );
  assert.deepEqual((await api("GET", "/workspace")).rooms, after.rooms);
});

test("demo one-room conflict rejects the whole class without mutation", async () => {
  const { api, preview } = await setup();
  const first = (await api("GET", "/workspace")).rooms.find(
    (r) => r.id === preview.rooms[0].id,
  );
  await api("PATCH", `/rooms/${first.id}`, {
    ...first,
    pricePeriods: [{ ...period, price: 20000 }],
  });
  const fresh = await api(
    "GET",
    "/resorts/altun/class-pricing?category=standard",
  );
  const before = await api("GET", "/workspace");
  await assert.rejects(
    api(
      "POST",
      "/resorts/altun/class-pricing",
      classPricingPayload(fresh, period),
    ),
    (error) => error.status === 409,
  );
  const after = await api("GET", "/workspace");
  assert.deepEqual(after.rooms, before.rooms);
  assert.deepEqual(after.audit, before.audit);
});

test("demo enforces manager ownership and denies accountant class price mutation", async () => {
  const { api, preview } = await setup();
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  await assert.rejects(
    api("GET", "/resorts/kokterek/class-pricing?category=standard"),
    (error) => error.status === 403,
  );
  await api("POST", "/auth/login", { accountId: "admin" });
  const accountant = await api("POST", "/accounts", {
    name: "Fictional accountant",
    login: "accountant@example.test",
    role: "accountant",
    status: "active",
    resortId: "altun",
  });
  await api("POST", "/auth/login", { accountId: accountant.id });
  await assert.rejects(
    api("GET", "/resorts/altun/class-pricing?category=standard"),
    (error) => error.status === 403,
  );
  await assert.rejects(
    api(
      "POST",
      "/resorts/altun/class-pricing",
      classPricingPayload(preview, period),
    ),
    (error) => error.status === 403,
  );
});
