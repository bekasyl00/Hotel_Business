import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parse, compileScript } from "@vue/compiler-sfc";
import * as Vue from "vue";
import * as children from "../src/features/create-booking/model/children.js";
import * as rules from "../src/entities/booking/model/rules.js";
import * as terms from "../src/entities/booking/model/payment-terms.js";
import { shiftDay } from "../src/entities/booking/model/occupancy.js";
import { i18n } from "../src/shared/i18n/index.js";

function mountEditor({ rooms, create } = {}) {
  let state;
  const calls = [];
  const { descriptor } = parse(
    readFileSync(
      new URL(
        "../src/features/create-booking/ui/BookingEditor.vue",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  const source = compileScript(descriptor, { id: "booking-party-behavior" })
    .content.replace(
      /import\s+\{([\s\S]*?)\}\s+from\s+["']([^"']+)["'];/g,
      (_, names, path) =>
        `const {${names.replace(/\s+as\s+/g, ": ")}} = modules[${JSON.stringify(path)}];`,
    )
    .replace("export default", "return");
  const component = new Function("modules", source)({
    vue: Vue,
    "vue-i18n": { useI18n: () => ({ t: i18n.global.t }) },
    "../model/children.js": children,
    "@/shared/config": { isDemo: false },
    "@/shared/ui": { Modal: {} },
    "@/entities/guest-account": {
      useGuestAccountStore: () => ({
        authenticated: true,
        restore: async () => {},
      }),
    },
    "@/shared/lib": { money: String, dateLabel: String },
    "@/entities/booking": {
      ...rules,
      ...terms,
      shiftDay,
      propertyToday: () => "2026-11-10",
      useBookingStore: () => ({
        create: async (payload, staff) => {
          calls.push(JSON.parse(JSON.stringify(payload)));
          return create ? create(payload, staff) : { id: "fictional-booking" };
        },
      }),
    },
  });
  const originalSetup = component.setup;
  component.setup = (props, ctx) => {
    state = originalSetup(props, ctx);
    return state;
  };
  component.render = () => Vue.h("div");
  const node = () => ({ children: [], parent: null });
  const renderer = Vue.createRenderer({
    createElement: node,
    createText: node,
    createComment: node,
    insert(child, parent) {
      child.parent = parent;
      parent.children.push(child);
    },
    remove() {},
    parentNode: (child) => child.parent,
    nextSibling: () => null,
    setText() {},
    setElementText() {},
    patchProp() {},
  });
  const room = {
    id: "small",
    category: "standard",
    number: "101",
    title: "Standard",
    status: "active",
    capacity: 2,
    price: 10000,
  };
  const app = renderer.createApp(component, {
    resort: { id: "fixture", bookingFeePercent: 10, timeZone: "Asia/Almaty" },
    rooms: rooms || [room, { ...room, id: "large", capacity: 4 }],
    tariffs: [
      {
        id: "stay",
        status: "active",
        supplement: 1000,
        childrenUnderTwoFree: true,
      },
    ],
    preset: { guests: 2, start: "2026-11-17", end: "2026-11-20" },
    staff: false,
  });
  app.mount(node());
  return { state, calls, close: () => app.unmount() };
}

test("add/remove child changes total, preserves older guests and remaining child fields", async () => {
  const { state, close } = mountEditor();
  try {
    state.addChild();
    assert.equal(state.adults.value, 2);
    assert.equal(state.form.guests, 3);
    assert.equal(state.form.roomId, "large");
    state.children.value[0].iin = "251212000000";
    state.addChild();
    state.children.value[1].iin = "151201000000";
    assert.equal(state.form.guests, 4);
    assert.deepEqual(state.form.childrenAges, [0, 10]);
    assert.equal(state.price.value.freeChildren, 1);
    assert.equal(state.price.value.total, 99000);
    assert.equal(state.displayPrice.value.total, 108900);
    assert.equal(state.settlement.value.onlineAmount, 9900);
    assert.equal(state.settlement.value.onsiteAmount, 99000);
    state.addChild();
    assert.equal(state.children.value.length, 2);
    const keptId = state.children.value[1].id;
    state.removeChild(state.children.value[0].id);
    assert.equal(state.form.guests, 3);
    assert.equal(state.adults.value, 2);
    assert.equal(state.children.value[0].id, keptId);
    assert.equal(state.children.value[0].iin, "151201000000");
    assert.deepEqual(state.form.childrenAges, [10]);
    assert.equal(state.price.value.freeChildren, 0);
    state.adults.value = 1;
    await Vue.nextTick();
    assert.equal(state.form.guests, 2);
    assert.equal(state.children.value[0].id, keptId);
  } finally {
    close();
  }
});

test("birth prefix gives month preview before completion; arrival changes recompute child eligibility", () => {
  const { state, close } = mountEditor();
  try {
    state.addChild();
    state.children.value[0].iin = "251212";
    assert.equal(state.childPreviews.value[0].birth, "2025-12-12");
    assert.match(state.ageDescription(state.childPreviews.value[0]), /11 мес/);
    assert.equal(state.price.value, null);
    state.children.value[0].iin = "121118000000";
    assert.deepEqual(state.form.childrenAges, [13]);
    state.form.start = "2026-11-18";
    assert.equal(state.childPreviews.value[0].status, "overChildAge");
    assert.match(state.childError(0), /14/);
    assert.equal(state.price.value, null);
    state.children.value[0].iin = "230229";
    assert.equal(state.childPreviews.value[0].status, "invalidBirthDate");
    assert.ok(state.childError(0));
  } finally {
    close();
  }
});

test("capacity and invalid older-guest input block submission without deleting children", async () => {
  const { state, calls, close } = mountEditor({
    rooms: [
      {
        id: "small",
        category: "standard",
        status: "active",
        capacity: 2,
        price: 10000,
      },
    ],
  });
  try {
    state.addChild();
    state.children.value[0].iin = "251212000000";
    assert.equal(state.form.guests, 3);
    assert.ok(state.capacityError.value);
    await state.save();
    assert.equal(calls.length, 0);
    state.adults.value = "";
    assert.ok(state.partyError.value);
    assert.equal(state.form.guests, null);
    assert.equal(state.children.value[0].iin, "251212000000");
    state.adults.value = 1;
    assert.equal(state.form.guests, 2);
    assert.equal(state.partyError.value, "");
    assert.equal(state.capacityError.value, "");
    assert.ok(state.price.value);
  } finally {
    close();
  }
});

test("transport receives only ages/DOB and stable retry IDs, including equal-age DOB corrections", async () => {
  const { state, calls, close } = mountEditor({
    create: () => {
      throw new Error("fictional transport interruption");
    },
  });
  try {
    state.addChild();
    state.children.value[0].iin = "251212000000";
    await state.save();
    await state.save();
    assert.equal(calls[0].guests, 3);
    assert.deepEqual(calls[0].childrenAges, [0]);
    assert.deepEqual(calls[0].childrenBirthDates, ["2025-12-12"]);
    assert.equal(calls[0].requestId, calls[1].requestId);
    assert.equal(calls[0].guestLabel, undefined);
    assert.equal(calls[0].guestPhone, undefined);
    assert.doesNotMatch(JSON.stringify(calls), /251212000000|"iin"/);
    state.children.value[0].iin = "251213000000";
    await state.save();
    assert.deepEqual(calls[2].childrenAges, [0]);
    assert.notEqual(calls[2].requestId, calls[1].requestId);
    state.children.value[0].iin = "251213111111";
    await state.save();
    assert.equal(calls[3].requestId, calls[2].requestId);
  } finally {
    close();
  }
});
