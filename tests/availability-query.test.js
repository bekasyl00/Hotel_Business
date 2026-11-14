import test from "node:test";
import assert from "node:assert/strict";
import { effectScope, reactive } from "vue";
import { configureTransport } from "../src/shared/api/index.js";
import { useAvailability } from "../src/entities/booking/model/use-availability.js";
import { dateAfter } from "../src/entities/booking/model/rules.js";

function setup(t) {
  const scope = effectScope();
  const dates = reactive({
    start: dateAfter(7),
    end: dateAfter(10),
    guests: 2,
  });
  const query = scope.run(() => useAvailability(dates));
  t.after(() => scope.stop());
  return { dates, query, scope };
}

function pendingRequests() {
  const calls = [];
  configureTransport(
    (method, path) =>
      new Promise((resolve, reject) => {
        calls.push({ method, path, resolve, reject });
      }),
  );
  return calls;
}

test("calendar selection sends the chosen dates and guest count", async (t) => {
  const { dates, query } = setup(t);
  let requested;
  configureTransport(async (method, path) => {
    requested = { method, path };
    return { roomIds: ["room-a"] };
  });
  await query.selectCalendarDates({ start: dateAfter(12), end: dateAfter(15) });
  assert.equal(requested.method, "GET");
  assert.equal(requested.path, "/availability?" + new URLSearchParams(dates));
  assert.deepEqual(query.roomIds.value, ["room-a"]);
  assert.equal(query.searching.value, false);
});

test("an earlier response cannot replace availability for new dates", async (t) => {
  const { dates, query } = setup(t);
  const calls = pendingRequests();
  const first = query.checkDates();
  dates.end = dateAfter(11);
  assert.equal(query.searching.value, false);
  const second = query.checkDates();
  calls[1].resolve({ roomIds: ["new-room"] });
  await second;
  calls[0].resolve({ roomIds: ["old-room"] });
  await first;
  assert.deepEqual(query.roomIds.value, ["new-room"]);
  assert.equal(query.searchError.value, "");
});

test("invalid dates suppress requests and invalidate pending results", async (t) => {
  const { dates, query } = setup(t);
  const calls = pendingRequests();
  const first = query.checkDates();
  dates.end = dates.start;
  await query.checkDates();
  assert.equal(calls.length, 1);
  assert.ok(query.searchError.value);
  calls[0].resolve({ roomIds: ["old-room"] });
  await first;
  assert.equal(query.roomIds.value, null);
  assert.equal(query.searching.value, false);
});

test("route invalidation and scope disposal ignore stale failures", async (t) => {
  const { query, scope } = setup(t);
  const calls = pendingRequests();
  const first = query.checkDates();
  query.invalidate();
  calls[0].reject(new Error("old route failure"));
  await first;
  assert.equal(query.searchError.value, "");
  const second = query.checkDates();
  scope.stop();
  calls[1].resolve({ roomIds: ["disposed-room"] });
  await second;
  assert.equal(query.roomIds.value, null);
  assert.equal(query.searching.value, false);
});

test("current request failures remain visible and a retry recovers", async (t) => {
  const { query } = setup(t);
  configureTransport(async () => {
    throw new Error("offline");
  });
  await query.checkDates();
  assert.equal(query.searchError.value, "offline");
  assert.equal(query.searching.value, false);
  configureTransport(async () => ({ roomIds: [] }));
  await query.checkDates();
  assert.equal(query.searchError.value, "");
  assert.deepEqual(query.roomIds.value, []);
});
