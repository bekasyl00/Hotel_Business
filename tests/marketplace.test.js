import test from "node:test";
import assert from "node:assert/strict";
import {
  createDemoTransport,
  DATABASE_KEY,
} from "../src/app/providers/demo.js";
import {
  freezePolicy,
  refundPreview,
  safeUrl,
} from "../src/app/providers/demo-marketplace.js";
import { dateAfter } from "../src/entities/booking/rules.js";

function setup() {
  const data = new Map(),
    accounts = new Map();
  const memory = (map) => ({
    getItem: (k) => map.get(k) || null,
    setItem: (k, v) => map.set(k, v),
    removeItem: (k) => map.delete(k),
  });
  const storage = memory(data);
  const api = createDemoTransport({
    storage,
    session: memory(accounts),
    delay: 0,
  });
  const mutate = (fn) => {
    const db = JSON.parse(storage.getItem(DATABASE_KEY));
    fn(db);
    storage.setItem(DATABASE_KEY, JSON.stringify(db));
  };
  return { api, mutate };
}
const booking = () => ({
  roomId: "altun-111",
  tariffId: "altun-meals",
  start: dateAfter(7),
  end: dateAfter(10),
  guests: 2,
  requestId: crypto.randomUUID(),
});

test("refund boundaries use frozen advertised checkin; settled refund never changes", () => {
  const terms = freezePolicy({ checkInTime: "16:30" }, "2030-05-10");
  assert.equal(terms.checkinAt, "2030-05-10T16:30:00+05:00");
  const b = {
    cancellationPolicy: terms,
    payment: { status: "paid", amount: 100001 },
  };
  const checkin = Date.parse(terms.checkinAt);
  for (const [hours, expected] of [
    [48, 100],
    [47.999, 70],
    [24, 70],
    [23.999, 0],
    [-1, 0],
  ]) {
    const result = refundPreview(b, false, checkin - hours * 3600000);
    assert.equal(result.refundPercent, expected);
    assert.equal(result.refundAmount, Math.floor((100001 * expected) / 100));
    assert.equal(
      refundPreview(b, true, checkin - hours * 3600000).refundPercent,
      expected,
    );
  }
  b.cancellation = refundPreview(b, false, checkin - 36 * 3600000);
  b.payment.status = "partially_refunded";
  assert.equal(refundPreview(b, false, checkin + 1000).refundAmount, 70000);
  assert.equal(refundPreview(b).finalized, true);
});

test("discount and checkin survive later catalogue changes", async () => {
  const { api } = setup();
  await api("POST", "/auth/login", { accountId: "admin" });
  let workspace = await api("GET", "/workspace");
  const resort = workspace.resorts.find((r) => r.id === "altun");
  const tariff = workspace.tariffs.find((t) => t.id === "altun-meals");
  await api("PATCH", `/resorts/${resort.id}`, {
    ...resort,
    checkInTime: "16:30",
  });
  await api("PATCH", `/tariffs/${tariff.id}`, {
    ...tariff,
    priceKind: "discount",
    discountPercent: 15,
  });
  const b = await api("POST", "/my-bookings", booking());
  assert.equal(b.total, 84150);
  assert.equal(b.cancellationPolicy.checkInTime, "16:30");
  workspace = await api("GET", "/workspace");
  await api("PATCH", `/resorts/${resort.id}`, {
    ...workspace.resorts.find((r) => r.id === resort.id),
    checkInTime: "12:00",
  });
  assert.equal(
    (await api("GET", "/my-bookings"))[0].cancellationPolicy.checkInTime,
    "16:30",
  );
});

test("payment confirms pending automatically; retry is idempotent and cancellation settles once", async () => {
  const { api } = setup();
  let b = await api("POST", "/my-bookings", booking());
  const pay = {
    bookingId: b.id,
    requestId: crypto.randomUUID(),
    outcome: "success",
  };
  assert.equal(b.status, "pending");
  assert.ok(b.holdExpiresAt);
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  await assert.rejects(
    api("PATCH", `/bookings/${b.id}`, {
      version: b.version,
      status: "confirmed",
    }),
  );
  const payment = await api("POST", "/payments/demo", pay);
  assert.equal(payment.status, "paid");
  b = (await api("GET", "/my-bookings")).find((x) => x.id === b.id);
  assert.equal(b.status, "confirmed");
  assert.equal((await api("POST", "/payments/demo", pay)).id, payment.id);
  await assert.rejects(
    api("POST", "/payments/demo", { ...pay, requestId: crypto.randomUUID() }),
    (e) => e.status === 409,
  );
  await api("PATCH", `/my-bookings/${b.id}`, {
    version: b.version,
    status: "cancelled",
  });
  const preview = await api("GET", `/cancellation-preview/${b.id}`);
  assert.equal(preview.refundAmount, 99000);
  assert.equal(preview.finalized, true);
  assert.equal((await api("POST", "/payments/demo", pay)).status, "refunded");
});

test("only completed verified stays can review; moderation hides private metadata", async () => {
  const { api, mutate } = setup();
  const b = await api("POST", "/my-bookings", booking());
  const payload = {
    bookingId: b.id,
    rating: 5,
    text: "Тестовый отзыв о состоявшемся отдыхе",
    photos: ["/assets/room.jpg"],
  };
  await assert.rejects(
    api("POST", "/reviews", payload),
    (e) => e.status === 403,
  );
  mutate((db) =>
    Object.assign(db.bookings[0], {
      status: "confirmed",
      start: dateAfter(-5),
      end: dateAfter(-1),
    }),
  );
  const review = await api("POST", "/reviews", payload);
  assert.equal((await api("GET", "/reviews?resortId=altun")).length, 0);
  await assert.rejects(
    api("POST", "/reviews", payload),
    (e) => e.status === 409,
  );
  await api("POST", "/auth/login", { accountId: "manager-arasan" });
  await assert.rejects(
    api("PATCH", `/reviews/${review.id}`, { version: 1, status: "approved" }),
    (e) => e.status === 403,
  );
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  await api("PATCH", `/reviews/${review.id}`, {
    version: 1,
    status: "approved",
    reply: "Спасибо!",
  });
  const visible = (await api("GET", "/resorts/altun")).reviews[0];
  assert.equal(visible.reply, "Спасибо!");
  assert.equal(visible.bookingId, undefined);
  assert.equal((await api("GET", "/my-bookings"))[0].reviewStatus, "approved");
});

test("staff sessions cannot review even an owned completed website booking", async () => {
  const { api, mutate } = setup();
  const b = await api("POST", "/my-bookings", booking());
  mutate((db) =>
    Object.assign(
      db.bookings.find((item) => item.id === b.id),
      {
        status: "confirmed",
        start: dateAfter(-5),
        end: dateAfter(-1),
      },
    ),
  );
  const payload = {
    bookingId: b.id,
    rating: 5,
    text: "Хорошее демо-проживание.",
    photos: [],
  };
  for (const accountId of ["manager-altun", "admin"]) {
    await api("POST", "/auth/login", { accountId });
    await assert.rejects(
      api("POST", "/reviews", payload),
      (e) => e.status === 403,
    );
  }
  await api("POST", "/auth/logout");
  const review = await api("POST", "/reviews", payload);
  assert.equal(review.status, "pending");
});

test("media URL rejects credentialed, malformed and traversing references", () => {
  for (const url of [
    "javascript:alert(1)",
    "https://user:secret@example.test/image.jpg",
    "https://[invalid",
    "/media/../secret",
    "/media/%2e%2e/secret",
    "//example.test/photo",
    "/media/file\n.jpg",
  ])
    assert.equal(safeUrl(url), false, url);
  for (const url of [
    "https://example.test/photo.jpg",
    "/media/photo.jpg",
    "/assets/room.jpg",
  ])
    assert.equal(safeUrl(url), true, url);
});

test("guest profile persists across reloads and staff history is tenant scoped", async () => {
  const { api } = setup();
  const first = (await api("GET", "/profile")).profile;
  const changed = await api("PATCH", "/profile", {
    name: "Демо-гость",
    phone: "+70000000000",
  });
  assert.equal(changed.profile.id, first.id);
  await assert.rejects(
    api("PATCH", "/profile", {
      name: "Демо",
      phone: "+70000000000",
      owner: "other",
    }),
  );
  const a = await api("POST", "/my-bookings", booking());
  await api("POST", "/my-bookings", {
    ...booking(),
    roomId: "arasan-211",
    tariffId: "arasan-meals",
  });
  assert.equal(a.guestProfileId, first.id);
  assert.equal(a.guestLabel, "Демо-гость");
  assert.equal((await api("GET", "/profile")).bookings.length, 2);
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  const scoped = await api("GET", `/guests/${first.id}`);
  assert.equal(scoped.bookings.length, 1);
  assert.equal(scoped.bookings[0].resortId, "altun");
  await api("POST", "/auth/logout");
  await assert.rejects(
    api("GET", `/guests/${first.id}`),
    (e) => e.status === 401,
  );
});

test("demo receipt remains original after profile/catalogue edits and refunds", async () => {
  const { api } = setup();
  let b = await api("POST", "/my-bookings", booking());
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  await assert.rejects(
    api("PATCH", `/bookings/${b.id}`, {
      version: b.version,
      status: "confirmed",
    }),
  );
  const p = await api("POST", "/payments/demo", {
    bookingId: b.id,
    requestId: crypto.randomUUID(),
    outcome: "success",
  });
  b = (await api("GET", "/my-bookings")).find((x) => x.id === b.id);
  const original = (await api("GET", `/receipts/${p.id}`)).receipt;
  await api("PATCH", "/profile", {
    name: "Другое демо-имя",
    phone: "+70000000001",
  });
  const resort = (await api("GET", "/workspace")).resorts[0];
  await api("PATCH", `/resorts/${resort.id}`, {
    ...Object.fromEntries(
      Object.entries(resort).filter(([key]) => key !== "commissionPercent"),
    ),
    address: "Новый адрес",
  });
  await api("PATCH", `/my-bookings/${b.id}`, {
    version: b.version,
    status: "cancelled",
  });
  const refunded = await api("GET", `/receipts/${p.id}`);
  assert.deepEqual(refunded.receipt, original);
  assert.equal(refunded.receipt.source, "demo");
  assert.equal(refunded.refund.amount, p.amount);
  assert.equal(refunded.payment.status, "refunded");
});

test("legacy demo receipts are restored once and remain frozen after catalogue edits", async () => {
  const { api, mutate } = setup();
  let b = await api("POST", "/my-bookings", booking());
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  await assert.rejects(
    api("PATCH", `/bookings/${b.id}`, {
      version: b.version,
      status: "confirmed",
    }),
  );
  const p = await api("POST", "/payments/demo", {
    bookingId: b.id,
    requestId: crypto.randomUUID(),
    outcome: "success",
  });
  mutate((db) => {
    delete db.payments.find((payment) => payment.id === p.id).receipt;
    delete db.bookings.find((item) => item.id === b.id).payment.receipt;
  });
  const restored = (await api("GET", `/receipts/${p.id}`)).receipt;
  assert.equal(restored.legacySnapshot, true);
  assert.match(restored.notice, /Восстановлена при первом открытии/);
  const resort = (await api("GET", "/workspace")).resorts[0];
  await api("PATCH", `/resorts/${resort.id}`, {
    ...Object.fromEntries(
      Object.entries(resort).filter(([key]) => key !== "commissionPercent"),
    ),
    address: "Изменённый после восстановления адрес",
  });
  assert.deepEqual((await api("GET", `/receipts/${p.id}`)).receipt, restored);
  mutate((db) => {
    assert.deepEqual(
      db.bookings.find((item) => item.id === b.id).payment.receipt,
      restored,
    );
    assert.deepEqual(
      db.payments.find((payment) => payment.id === p.id).receipt,
      restored,
    );
    assert.equal(
      db.audit.filter((event) => event.action === "restore_receipt").length,
      1,
    );
  });
});

test("arrival needs payment/date/scope/version; checked-in bookings cannot cancel", async () => {
  const { api, mutate } = setup();
  let b = await api("POST", "/my-bookings", booking());
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  await assert.rejects(
    api("PATCH", `/bookings/${b.id}`, {
      version: b.version,
      status: "confirmed",
    }),
  );
  await assert.rejects(
    api("POST", `/bookings/${b.id}/check-in`, { version: b.version }),
    (e) => e.status === 409,
  );
  await api("POST", "/payments/demo", {
    bookingId: b.id,
    requestId: crypto.randomUUID(),
    outcome: "success",
  });
  await assert.rejects(
    api("POST", `/bookings/${b.id}/check-in`, { version: b.version }),
    (e) => e.status === 409,
  );
  b = (await api("GET", "/my-bookings")).find((x) => x.id === b.id);
  mutate((db) => {
    const stay = db.bookings.find((item) => item.id === b.id);
    stay.start = "2000-01-01";
    stay.end = "2099-01-01";
  });
  await api("POST", "/auth/login", { accountId: "manager-arasan" });
  await assert.rejects(
    api("POST", `/bookings/${b.id}/check-in`, { version: b.version }),
    (e) => e.status === 403,
  );
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  const checked = await api("POST", `/bookings/${b.id}/check-in`, {
    version: b.version,
  });
  assert.equal(checked.stayStatus, "in_house");
  await assert.rejects(
    api("PATCH", `/my-bookings/${b.id}`, {
      version: checked.version,
      status: "cancelled",
    }),
    (e) => e.status === 409,
  );
  await assert.rejects(
    api("POST", `/bookings/${b.id}/check-out`, { version: b.version }),
    (e) => e.status === 409,
  );
  assert.equal(
    (
      await api("POST", `/bookings/${b.id}/check-out`, {
        version: checked.version,
      })
    ).stayStatus,
    "checked_out",
  );
});

test("expired demo holds release inventory and cannot be paid", async () => {
  const { api, mutate } = setup();
  const first = await api("POST", "/my-bookings", booking());
  mutate((db) => {
    db.bookings.find((b) => b.id === first.id).holdExpiresAt = new Date(
      Date.now() - 1000,
    ).toISOString();
  });
  await assert.rejects(
    api("POST", "/payments/demo", {
      bookingId: first.id,
      requestId: crypto.randomUUID(),
      outcome: "success",
    }),
    (e) => e.status === 409,
  );
  assert.equal((await api("GET", "/my-bookings"))[0].status, "expired");
  const second = await api("POST", "/my-bookings", booking());
  assert.equal(second.status, "pending");
});

test("admin commission setting is frozen for each order and protected from managers", async () => {
  const { api } = setup();
  await api("POST", "/auth/login", { accountId: "admin" });
  let resort = (await api("GET", "/workspace")).resorts.find(
    (r) => r.id === "altun",
  );
  resort = await api("PATCH", `/resorts/${resort.id}`, {
    ...resort,
    commissionPercent: "7.25",
  });
  const b = await api("POST", "/my-bookings", booking());
  await api("PATCH", `/resorts/${resort.id}`, {
    ...resort,
    commissionPercent: "10",
  });
  const stored = (await api("GET", "/workspace")).bookings.find(
    (x) => x.id === b.id,
  );
  assert.equal(stored.commissionTerms.amount, 7178);
  assert.equal(stored.commissionTerms.resortAmount, 91822);
  assert.equal(stored.commissionTerms.percent, "7.25");
  assert.equal(
    "commissionPercent" in (await api("GET", "/catalog")).resorts[0],
    false,
  );
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  resort = (await api("GET", "/workspace")).resorts[0];
  await assert.rejects(
    api("PATCH", `/resorts/${resort.id}`, {
      ...resort,
      commissionPercent: "0",
    }),
    (e) => e.status === 403,
  );
});

test("staff-created demo orders are booked by payment, not approval", async () => {
  const { api } = setup();
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  const b = await api("POST", "/bookings", {
    ...booking(),
    guestLabel: "Демо-гость",
  });
  await assert.rejects(
    api("PATCH", `/bookings/${b.id}`, {
      status: "confirmed",
      version: b.version,
    }),
  );
  await api("POST", "/payments/demo/staff", {
    bookingId: b.id,
    requestId: crypto.randomUUID(),
    outcome: "success",
  });
  assert.equal(
    (await api("GET", "/workspace")).bookings.find((x) => x.id === b.id).status,
    "confirmed",
  );
});
