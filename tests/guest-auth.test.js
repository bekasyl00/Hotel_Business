import test from "node:test";
import assert from "node:assert/strict";
import {
  createDemoTransport,
  DATABASE_KEY,
} from "../src/app/providers/demo.js";
import { dateAfter } from "../src/entities/booking/rules.js";
import { normalizePhone } from "../src/app/providers/demo-guest-auth.js";

const phone = "+77000000001";
const password = "Demo-only-secret!2030";
const memory = () => {
  const data = new Map();
  return {
    getItem: (k) => data.get(k) || null,
    setItem: (k, v) => data.set(k, v),
    removeItem: (k) => data.delete(k),
  };
};
function setup() {
  const storage = memory();
  const device = () =>
    createDemoTransport({ storage, session: memory(), delay: 0 });
  const api = device();
  const db = () => JSON.parse(storage.getItem(DATABASE_KEY));
  const mutate = (fn) => {
    const value = db();
    fn(value);
    storage.setItem(DATABASE_KEY, JSON.stringify(value));
  };
  return { api, device, db, mutate };
}
async function register(api) {
  const c = await api("POST", "/guest-auth/challenges", {
    phone,
    purpose: "register",
  });
  return api("POST", "/guest-auth/register", {
    challengeId: c.challengeId,
    code: c.demoCode,
    name: "Demo guest",
    password,
  });
}
const booking = () => ({
  roomId: "altun-111",
  tariffId: "altun-meals",
  start: dateAfter(10),
  end: dateAfter(12),
  guests: 1,
  requestId: crypto.randomUUID(),
});

test("phone auth normalizes KZ numbers and rejects email/non-mobile values", () => {
  assert.equal(normalizePhone("8 (700) 000-00-01"), phone);
  assert.equal(normalizePhone("+7 700 000 00 01"), phone);
  for (const value of [
    "a@example.com",
    "+15555555555",
    "+7700000000",
    "+70000000000",
  ])
    assert.throws(() => normalizePhone(value));
});
test("registration adopts only current anonymous history and hides it after logout", async () => {
  const { api, db } = setup();
  const before = (await api("GET", "/profile")).profile;
  const b = await api("POST", "/my-bookings", booking());
  const signed = await register(api);
  assert.equal(signed.authenticated, true);
  assert.equal(signed.profile.id, before.id);
  assert.equal((await api("GET", "/my-bookings"))[0].id, b.id);
  const raw = JSON.stringify(db());
  assert.equal(raw.includes(password), false);
  assert.equal(db().guestAccounts[0].passwordHash.length, 64);
  assert.equal(db().viewerId, undefined);
  await assert.rejects(
    api("PATCH", "/profile", { name: "Demo guest", phone: "+77000000002" }),
  );
  await api("POST", "/guest-auth/logout", {});
  assert.equal((await api("GET", "/guest-auth/session")).authenticated, false);
  assert.equal((await api("GET", "/my-bookings")).length, 0);
});
test("login uses account ownership without merging anonymous bookings", async () => {
  const { api } = setup();
  await register(api);
  const own = await api("POST", "/my-bookings", booking());
  await api("POST", "/guest-auth/logout", {});
  const anonymous = await api("POST", "/my-bookings", {
    ...booking(),
    start: dateAfter(20),
    end: dateAfter(22),
  });
  await assert.rejects(
    api("POST", "/guest-auth/login", { phone, password: "wrong" }),
    (e) => e.status === 401,
  );
  await api("POST", "/guest-auth/login", { phone, password });
  assert.deepEqual(
    (await api("GET", "/my-bookings")).map((b) => b.id),
    [own.id],
  );
  assert.notEqual(own.id, anonymous.id);
  await api("POST", "/guest-auth/logout", {});
  assert.equal((await api("GET", "/my-bookings")).length, 0);
});
test("reset revokes other sessions and requires the new password", async () => {
  const { api, device, mutate } = setup();
  await register(api);
  const second = device();
  await second("POST", "/guest-auth/login", { phone, password });
  mutate((db) => db.guestChallenges.forEach((c) => (c.createdAt -= 61000)));
  const c = await api("POST", "/guest-auth/challenges", {
    phone,
    purpose: "reset",
  });
  const replacement = "New-demo-password!2031";
  await api("POST", "/guest-auth/reset", {
    challengeId: c.challengeId,
    code: c.demoCode,
    password: replacement,
  });
  assert.equal(
    (await second("GET", "/guest-auth/session")).authenticated,
    false,
  );
  await assert.rejects(
    second("POST", "/guest-auth/login", { phone, password }),
    (e) => e.status === 401,
  );
  assert.equal(
    (
      await second("POST", "/guest-auth/login", {
        phone,
        password: replacement,
      })
    ).authenticated,
    true,
  );
});
test("OTP is bound to browser and purpose, expires and stops after five failed attempts", async () => {
  const { api, device, mutate } = setup();
  const c = await api("POST", "/guest-auth/challenges", {
    phone,
    purpose: "register",
  });
  const payload = {
    challengeId: c.challengeId,
    code: c.demoCode,
    name: "Demo",
    password,
  };
  await assert.rejects(device()("POST", "/guest-auth/register", payload));
  await assert.rejects(api("POST", "/guest-auth/reset", payload));
  await assert.rejects(
    api("POST", "/guest-auth/challenges", { phone, purpose: "register" }),
    (e) => e.status === 429,
  );
  for (let i = 0; i < 5; i++)
    await assert.rejects(
      api("POST", "/guest-auth/register", {
        ...payload,
        code: c.demoCode === "000000" ? "111111" : "000000",
      }),
    );
  await assert.rejects(api("POST", "/guest-auth/register", payload));
  mutate((db) => {
    db.guestChallenges = [];
    db.guestAttempts = [];
  });
  const next = await api("POST", "/guest-auth/challenges", {
    phone,
    purpose: "register",
  });
  mutate((db) => db.guestChallenges.forEach((c) => (c.expiresAt = 0)));
  await assert.rejects(
    api("POST", "/guest-auth/register", {
      ...payload,
      challengeId: next.challengeId,
      code: next.demoCode,
    }),
    (e) => e.code === "code_expired",
  );
});
