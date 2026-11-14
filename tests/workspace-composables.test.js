import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as Vue from "vue";
import { useWorkspaceFilters } from "../src/pages/workspace/model/use-workspace-filters.js";

function loadComposable(name, dependencies) {
  const source = readFileSync(
    new URL(`../src/pages/workspace/model/${name}.js`, import.meta.url),
    "utf8",
  )
    .replace(
      /import\s*\{([^}]+)\}\s*from\s*"([^"]+)";/g,
      (_, names, path) =>
        `const {${names}} = modules[${JSON.stringify(path)}];`,
    )
    .replace("export function", "return function");
  return new Function("modules", source)({ vue: Vue, ...dependencies });
}

function notificationState(request) {
  const useNotifications = loadComposable("use-workspace-notifications", {
    "@/shared/api": { request },
  });
  const inputs = {
    session: { user: { id: "staff" }, isAccountant: false },
    selected: Vue.ref("resort-a"),
    error: Vue.ref(""),
    busy: Vue.ref(false),
  };
  return { ...inputs, ...useNotifications(inputs) };
}

test("workspace notification read replaces the item and read-all keeps resort scope", async () => {
  const calls = [];
  const state = notificationState(async (method, path, body) => {
    calls.push({ method, path, body });
    if (path.endsWith("/read")) return { id: "one", readAt: "now" };
    if (path.endsWith("read-all")) return { unreadCount: 0 };
    return { items: [{ id: "one", readAt: "now" }], unreadCount: 0 };
  });
  state.notifications.value = [
    { id: "one", readAt: null },
    { id: "two", readAt: null },
  ];
  state.unreadNotifications.value = 2;
  await state.markNotificationRead(state.notifications.value[0]);
  assert.equal(state.notifications.value[0].readAt, "now");
  assert.equal(state.unreadNotifications.value, 1);
  await state.markNotificationRead(state.notifications.value[0]);
  assert.equal(calls.length, 1);
  await state.markAllNotificationsRead();
  assert.deepEqual(calls[1].body, { resortId: "resort-a" });
  assert.equal(state.busy.value, false);
  assert.equal(state.unreadNotifications.value, 0);
});

test("workspace notifications retain data on failure and skip accountant requests", async () => {
  let calls = 0;
  const state = notificationState(async () => {
    calls++;
    throw new Error("offline");
  });
  state.notifications.value = [{ id: "one" }];
  await state.loadNotifications();
  assert.equal(state.error.value, "offline");
  assert.equal(state.notifications.value[0].id, "one");
  state.session.isAccountant = true;
  await state.loadNotifications();
  assert.equal(calls, 1);
});

test("workspace filters preserve resort, payment and actual stay state semantics", () => {
  const inputs = {
    catalog: Vue.reactive({ resorts: [{ id: "a" }], rooms: [], tariffs: [] }),
    bookings: Vue.reactive({
      items: [
        {
          id: "paid",
          resortId: "a",
          createdAt: "2026-01-01",
          status: "confirmed",
          payment: { status: "paid" },
          stayStatus: "in_house",
        },
        {
          id: "departed",
          resortId: "a",
          createdAt: "2026-01-02",
          status: "confirmed",
          payment: { status: "paid" },
          stayStatus: "checked_out",
        },
        {
          id: "other",
          resortId: "b",
          createdAt: "2026-01-03",
          status: "confirmed",
          payment: { status: "paid" },
        },
      ],
    }),
    session: Vue.reactive({ isAdmin: false }),
    selected: Vue.ref("a"),
    query: Vue.ref(""),
    status: Vue.ref("paid"),
    accounts: Vue.ref([]),
    audit: Vue.ref([
      { id: "global", resortId: null },
      { id: "local", resortId: "a" },
    ]),
    reviews: Vue.ref([]),
    notifications: Vue.ref([]),
  };
  const state = useWorkspaceFilters(inputs);
  assert.deepEqual(
    state.filteredBookings.value.map((item) => item.id),
    ["paid"],
  );
  inputs.status.value = "checked_out";
  assert.deepEqual(
    state.filteredBookings.value.map((item) => item.id),
    ["departed"],
  );
  assert.deepEqual(
    state.filteredAudit.value.map((item) => item.id),
    ["local"],
  );
  inputs.session.isAdmin = true;
  assert.equal(state.filteredAudit.value.length, 2);
  inputs.selected.value = "b";
  assert.equal(state.filteredBookings.value.length, 0);
});

test("workspace booking commands preserve versions and surface failed writes in the stay card", async () => {
  const calls = [];
  let fail = false;
  const useBookings = loadComposable("use-workspace-bookings", {
    "@/entities/booking": { propertyToday: () => "2026-11-14" },
    "@/shared/lib": { money: String },
    "@/shared/api": {
      request: async (...args) => {
        calls.push(args);
        if (fail) throw new Error("stale version");
      },
    },
  });
  const booking = {
    id: "b",
    resortId: "a",
    version: 3,
    status: "confirmed",
    payment: { status: "paid" },
    start: "2026-11-13",
    end: "2026-11-16",
  };
  let reloads = 0;
  const inputs = {
    session: { isAccountant: false },
    bookings: { items: [booking] },
    selected: Vue.ref("a"),
    current: Vue.ref({}),
    editor: Vue.ref(null),
    confirm: Vue.ref(null),
    busy: Vue.ref(false),
    error: Vue.ref(""),
    notice: Vue.ref(""),
    load: async () => {
      reloads++;
    },
    t: (value) => value,
  };
  const scope = Vue.effectScope();
  const state = scope.run(() => useBookings(inputs));
  state.focusedId.value = "b";
  await Vue.nextTick();
  assert.equal(state.canCheckIn(booking), true);
  await state.saveNotes("staff only");
  assert.deepEqual(calls[0], [
    "POST",
    "/bookings/b/notes",
    { version: 3, staffNotes: "staff only" },
  ]);
  assert.equal(reloads, 1);
  fail = true;
  await state.changeStay(booking, "check-out");
  assert.equal(state.detailError.value, "stale version");
  assert.equal(inputs.busy.value, false);
  assert.equal(reloads, 1);
  inputs.selected.value = "other";
  await Vue.nextTick();
  assert.equal(state.focusedId.value, null);
  scope.stop();
});

test("notification read retains server count beyond the loaded page and rejects stale list responses", async () => {
  let completeList;
  const state = notificationState(async (method) => {
    if (method === "GET")
      return new Promise((resolve) => {
        completeList = resolve;
      });
    return { id: "one", readAt: "now", unreadCount: 49 };
  });
  state.notifications.value = [{ id: "one", readAt: null }];
  state.unreadNotifications.value = 50;
  const pendingList = state.loadNotifications();
  await state.markNotificationRead(state.notifications.value[0]);
  assert.equal(state.unreadNotifications.value, 49);
  completeList({ items: [{ id: "one", readAt: null }], unreadCount: 50 });
  await pendingList;
  assert.equal(state.notifications.value[0].readAt, "now");
  assert.equal(state.unreadNotifications.value, 49);
});

test("concurrent reads of one notification decrement the demo counter once", async () => {
  let finish;
  let calls = 0;
  const state = notificationState(async () => {
    calls++;
    return new Promise((resolve) => {
      finish = resolve;
    });
  });
  const item = { id: "one", readAt: null };
  state.notifications.value = [item];
  state.unreadNotifications.value = 50;
  const first = state.markNotificationRead(item);
  await state.markNotificationRead(item);
  assert.equal(calls, 1);
  finish({ id: "one", readAt: "now" });
  await first;
  await state.markNotificationRead(item);
  assert.equal(calls, 1);
  assert.equal(state.unreadNotifications.value, 49);
});
