async function registerGuest(api) {
  const challenge = await api("POST", "/guest-auth/challenges", {
    phone: "+77000000001",
    purpose: "register",
  });
  await api("POST", "/guest-auth/register", {
    challengeId: challenge.challengeId,
    code: challenge.demoCode,
    name: "Демо-гость",
    password: "12345678",
  });
}
import test from "node:test";
import assert from "node:assert/strict";
import {
  createDemoTransport,
  DATABASE_KEY,
} from "../src/app/providers/demo.js";
import { dateAfter } from "../src/entities/booking/rules.js";
function memory() {
  const data = new Map();
  return {
    getItem: (k) => data.get(k) || null,
    setItem: (k, v) => data.set(k, v),
    removeItem: (k) => data.delete(k),
  };
}
async function setup() {
  const storage = memory(),
    session = memory(),
    api = createDemoTransport({ storage, session, delay: 0 });
  await registerGuest(api);
  await api("POST", "/auth/login", { accountId: "admin" });
  return { api, storage, session };
}
const booking = (roomId = "altun-111") => ({
  roomId,
  tariffId: "altun-meals",
  start: dateAfter(7),
  end: dateAfter(10),
  guests: 2,
  guestLabel: "Тестовый гость",
});
const newResort = {
  accountId: "admin",
  name: "Тестовый санаторий",
  city: "Сарыагаш",
  address: "Тестовый адрес",
  description: "",
  subtitle: "",
  feature: "Бассейн",
  lat: 41.385,
  lng: 69.061,
  status: "draft",
};
test("invalid child ages cannot create a demo booking or change the audit", async () => {
  const { api } = await setup();
  const before = await api("GET", "/workspace");
  for (const childrenAges of [[null], [18], [0, 1], "2", false]) {
    await assert.rejects(
      api("POST", "/bookings", { ...booking(), childrenAges }),
      (error) => error.status === 422,
    );
  }
  const after = await api("GET", "/workspace");
  assert.deepEqual(after.bookings, before.bookings);
  assert.deepEqual(after.audit, before.audit);
});
test("staff can update the opt-in child policy with a versioned partial tariff patch", async () => {
  const { api } = await setup();
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  const before = (await api("GET", "/workspace")).tariffs.find(
    (tariff) => tariff.id === "altun-meals",
  );
  const result = await api("PATCH", `/tariffs/${before.id}`, {
    version: before.version,
    childrenUnderTwoFree: true,
  });
  assert.equal(result.childrenUnderTwoFree, true);
  for (const field of [
    "name",
    "description",
    "supplement",
    "features",
    "status",
  ])
    assert.deepEqual(result[field], before[field]);
  await assert.rejects(
    api("PATCH", `/tariffs/${before.id}`, {
      version: before.version,
      childrenUnderTwoFree: false,
    }),
    (error) => error.status === 409,
  );
  await assert.rejects(
    api("PATCH", "/tariffs/arasan-meals", {
      version: 1,
      childrenUnderTwoFree: true,
    }),
    (error) => error.status === 403,
  );
});
test("manager sees only assigned tenant and cannot mutate foreign records or accounts", async () => {
  const { api } = await setup();
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  const data = await api("GET", "/workspace");
  assert.deepEqual(
    data.resorts.map((r) => r.id),
    ["altun"],
  );
  assert.ok(data.rooms.every((r) => r.resortId === "altun"));
  assert.equal(data.accounts.length, 0);
  assert.deepEqual(data.audit, []);
  await assert.rejects(
    api("POST", "/resorts", newResort),
    (e) => e.status === 403,
  );
  await assert.rejects(
    api("PATCH", "/rooms/arasan-211", { version: 1 }),
    (e) => e.status === 403,
  );
  await assert.rejects(api("POST", "/accounts", {}), (e) => e.status === 403);
  await api("POST", "/auth/logout");
  await assert.rejects(api("GET", "/workspace"), (e) => e.status === 401);
});
test("new resort requires inventory and tariff before publishing; published data reaches catalog", async () => {
  const { api } = await setup();
  let r = await api("POST", "/resorts", newResort);
  await assert.rejects(
    api("PATCH", "/resorts/" + r.id, { ...r, status: "published" }),
    /активный номер и тариф/,
  );
  await api("POST", "/rooms", {
    resortId: r.id,
    number: "101",
    category: "standard",
    title: "Стандарт",
    capacity: 2,
    area: 22,
    beds: "Две кровати",
    price: 18000,
    status: "active",
  });
  await api("POST", "/tariffs", {
    resortId: r.id,
    name: "Проживание",
    description: "",
    supplement: 0,
    features: "Wi-Fi",
    status: "active",
  });
  r = await api("PATCH", "/resorts/" + r.id, { ...r, status: "published" });
  assert.ok((await api("GET", "/catalog")).resorts.some((x) => x.id === r.id));
  assert.equal(
    (await api("GET", "/workspace")).audit.filter((a) => a.resortId === r.id)
      .length,
    4,
  );
});
test("booking collision, totals, availability, cancellation and immutable history", async () => {
  const { api } = await setup();
  const b = await api("POST", "/bookings", booking());
  assert.equal(b.total, 171000);
  await assert.rejects(
    api("POST", "/bookings", booking()),
    (e) => e.status === 409,
  );
  const available = await api(
    "GET",
    "/availability?" +
      new URLSearchParams({ start: b.start, end: b.end, guests: 2 }),
  );
  assert.ok(!available.roomIds.includes(b.roomId));
  await assert.rejects(
    api("DELETE", "/rooms/" + b.roomId, { version: 1 }),
    /историей бронирований/,
  );
  await api("PATCH", "/bookings/" + b.id, { status: "cancelled", version: 1 });
  const next = await api("POST", "/bookings", booking());
  assert.notEqual(next.id, b.id);
  const events = (await api("GET", "/workspace")).audit;
  const cancel = events.find((e) => e.action === "cancel");
  assert.equal(cancel.before.status, "pending");
  assert.equal(cancel.after.status, "cancelled");
});
test("stale versions and duplicate room numbers cannot silently overwrite records", async () => {
  const { api } = await setup();
  const room = (await api("GET", "/workspace")).rooms[0];
  await api("PATCH", "/rooms/" + room.id, { ...room, price: 30000 });
  await assert.rejects(
    api("PATCH", "/rooms/" + room.id, { ...room, price: 20000 }),
    (e) => e.status === 409,
  );
  await assert.rejects(api("POST", "/rooms", room), /уже существует/);
  const state = await api("GET", "/workspace");
  assert.equal(state.rooms[0].price, 30000);
  assert.equal(state.audit.filter((e) => e.entity === "rooms").length, 1);
});
test("public bookings are visible to staff, staff bookings stay out of guest booking list", async () => {
  const { api } = await setup();
  await api("POST", "/bookings", booking());
  await api("POST", "/auth/logout");
  const publicBooking = await api("POST", "/my-bookings", booking("altun-112"));
  const mine = await api("GET", "/my-bookings");
  assert.deepEqual(
    mine.map((b) => b.id),
    [publicBooking.id],
  );
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  assert.equal((await api("GET", "/workspace")).bookings.length, 2);
});
test("failed persistence and corrupted data do not report success or reset data", async () => {
  const { api, storage } = await setup();
  const initial = storage.getItem(DATABASE_KEY),
    save = storage.setItem;
  storage.setItem = () => {
    throw new Error("quota");
  };
  await assert.rejects(
    api("POST", "/resorts", newResort),
    (e) => e.status === 503,
  );
  assert.equal(storage.getItem(DATABASE_KEY), initial);
  storage.setItem = save;
  storage.setItem(DATABASE_KEY, "broken");
  await assert.rejects(api("GET", "/workspace"), (e) => e.status === 503);
  assert.equal(storage.getItem(DATABASE_KEY), "broken");
});
test("disabling a manager revokes subsequent workspace access", async () => {
  const { api, storage } = await setup();
  const managerSession = memory(),
    managerApi = createDemoTransport({
      storage,
      session: managerSession,
      delay: 0,
    });
  await managerApi("POST", "/auth/login", { accountId: "manager-altun" });
  const account = (await api("GET", "/workspace")).accounts.find(
    (a) => a.id === "manager-altun",
  );
  await api("PATCH", "/accounts/" + account.id, {
    ...account,
    status: "disabled",
  });
  assert.equal(await managerApi("GET", "/auth/session"), null);
  await assert.rejects(
    managerApi("GET", "/workspace"),
    (e) => e.status === 401,
  );
});

test("admin can reassign a manager; future requests use the new tenant", async () => {
  const { api, storage } = await setup();
  const account = (await api("GET", "/workspace")).accounts.find(
    (a) => a.id === "manager-altun",
  );
  const resorts = (await api("GET", "/workspace")).resorts;
  for (const [id, accountId] of [
    ["altun", "admin"],
    ["arasan", account.id],
  ]) {
    const r = resorts.find((r) => r.id === id);
    await api("PATCH", "/resorts/" + id, { ...r, accountId });
  }
  const manager = createDemoTransport({ storage, session: memory(), delay: 0 });
  await manager("POST", "/auth/login", { accountId: account.id });
  assert.deepEqual(
    (await manager("GET", "/workspace")).resorts.map((r) => r.id),
    ["arasan"],
  );
});

test("legacy guest bookings survive first initialization", async () => {
  const storage = memory();
  storage.setItem(
    "tynys:bookings:v1",
    JSON.stringify([
      {
        id: "legacy",
        resortId: "altun",
        resortName: "Altyn Bulak",
        roomId: "altun-standard",
        unit: "111",
        roomName: "Стандарт",
        tariffId: "meals",
        tariffName: "С питанием",
        start: dateAfter(7),
        end: dateAfter(10),
        guests: 2,
        total: 99000,
        status: "confirmed",
        createdAt: new Date().toISOString(),
      },
    ]),
  );
  const api = createDemoTransport({ storage, session: memory(), delay: 0 });
  const mine = await api("GET", "/my-bookings");
  assert.equal(mine[0].id, "legacy");
  assert.equal(mine[0].roomId, "altun-111");
  assert.equal(mine[0].tariffId, "altun-meals");
  assert.ok(storage.getItem("tynys:bookings:v1"));
});

test("deleting an unused room retains before-snapshot in scoped audit", async () => {
  const { api } = await setup();
  const room = await api("POST", "/rooms", {
    resortId: "altun",
    number: "999",
    category: "standard",
    title: "Стандарт",
    capacity: 2,
    area: 22,
    beds: "Две кровати",
    price: 20000,
    status: "active",
  });
  assert.equal(await api("DELETE", "/rooms/" + room.id, { version: 1 }), null);
  const data = await api("GET", "/workspace");
  assert.ok(!data.rooms.some((r) => r.id === room.id));
  const event = data.audit.find(
    (e) => e.entityId === room.id && e.action === "delete",
  );
  assert.equal(event.before.number, "999");
  assert.equal(event.after, null);
});
test("staff room-only booking locks the room price, while guest still requires a tariff", async () => {
  const { api } = await setup();
  const payload = booking();
  delete payload.tariffId;
  const workspace = await api("GET", "/workspace");
  const room = workspace.rooms.find((r) => r.id === payload.roomId);
  const created = await api("POST", "/bookings", payload);
  assert.equal(created.tariffId, null);
  assert.equal(created.pricingBasis, "room");
  assert.equal(created.total, room.price * 3 * 2);
  assert.equal(created.status, "pending");
  const paid = await api("POST", "/payments/demo/staff", {
    bookingId: created.id,
    requestId: crypto.randomUUID(),
    outcome: "success",
  });
  assert.ok(paid);
  assert.equal(
    (await api("GET", "/workspace")).bookings.find((b) => b.id === created.id)
      .status,
    "confirmed",
  );
  await assert.rejects(
    api("POST", "/my-bookings", {
      ...payload,
      start: dateAfter(12),
      end: dateAfter(14),
    }),
  );
});
test("staff notes enforce tenant and version, never copy free text to audit or guest output", async () => {
  const { api } = await setup();
  const created = await api("POST", "/bookings", booking());
  const result = await api("POST", `/bookings/${created.id}/notes`, {
    version: created.version,
    staffNotes: "Test internal note",
  });
  assert.equal(result.staffNotes, "Test internal note");
  assert.equal(result.version, created.version + 1);
  await assert.rejects(
    api("POST", `/bookings/${created.id}/notes`, {
      version: created.version,
      staffNotes: "Stale",
    }),
    (e) => e.status === 409,
  );
  assert.ok(
    !JSON.stringify((await api("GET", "/workspace")).audit).includes(
      "Test internal note",
    ),
  );
  await api("POST", "/auth/login", { accountId: "manager-arasan" });
  await assert.rejects(
    api("POST", `/bookings/${created.id}/notes`, {
      version: result.version,
      staffNotes: "Foreign",
    }),
    (e) => e.status === 403,
  );
});
