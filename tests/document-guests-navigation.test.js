import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parse, compileScript } from "@vue/compiler-sfc";
import * as Vue from "vue";
import * as Router from "vue-router";
import * as formHelpers from "../src/features/document-guests/model/form.js";

// Mount the actual component script with the real Vue router; only transport,
// translation and rendering are replaced. No guest data enters browser storage.
function documentGuestsComponent(request, capture) {
  const { descriptor } = parse(
    readFileSync(
      new URL(
        "../src/features/document-guests/ui/DocumentGuests.vue",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  const source = compileScript(descriptor, { id: "document-guests-navigation" })
    .content.replace(
      /import\s+\{([\s\S]*?)\}\s+from\s+["']([^"']+)["'];/g,
      (_, names, path) =>
        `const {${names.replace(/\s+as\s+/g, ": ")}} = modules[${JSON.stringify(path)}];`,
    )
    .replace("export default", "return");
  const component = new Function("modules", source)({
    vue: Vue,
    "vue-router": Router,
    "vue-i18n": { useI18n: () => ({ t: (key) => key }) },
    "@/shared/api": { request },
    "@/shared/config": { isDemo: false },
    "../model/form.js": formHelpers,
  });
  const setup = component.setup;
  component.setup = (props, context) => {
    const state = setup(props, context);
    capture(state);
    return state;
  };
  component.render = () => Vue.h("div");
  return component;
}

function memoryRenderer() {
  const node = () => ({ children: [], parent: null });
  return Vue.createRenderer({
    createElement: node,
    createText: node,
    createComment: node,
    insert(child, parent) {
      child.parent = parent;
      parent.children.push(child);
    },
    remove(child) {
      if (child.parent)
        child.parent.children = child.parent.children.filter(
          (item) => item !== child,
        );
    },
    parentNode: (child) => child.parent,
    nextSibling: () => null,
    setText() {},
    setElementText() {},
    patchProp() {},
  });
}

test("same-record staff navigation preserves a dirty roster until discard is confirmed", async () => {
  const previousWindow = globalThis.window;
  let confirmCount = 0,
    discard = false,
    state;
  globalThis.window = {
    addEventListener() {},
    removeEventListener() {},
    confirm() {
      confirmCount++;
      return discard;
    },
  };
  const DocumentGuests = documentGuestsComponent(
    async () => ({
      bookingId: "booking-a",
      version: 1,
      expectedGuests: 1,
      buyerIndex: 0,
      guests: [formHelpers.documentGuest({ fullName: "QA resident" })],
    }),
    (value) => {
      state = value;
    },
  );
  const Workspace = {
    setup() {
      const route = Router.useRoute(),
        open = Vue.ref(true);
      Vue.watch(
        () => route.params.section,
        () => {
          open.value = false;
        },
      );
      return () =>
        open.value
          ? Vue.h(DocumentGuests, { bookingId: "booking-a" })
          : Vue.h("main");
    },
  };
  const router = Router.createRouter({
    history: Router.createMemoryHistory(),
    routes: [{ path: "/staff/:section", component: Workspace }],
  });
  const app = memoryRenderer().createApp({
    render: () => Vue.h(Router.RouterView),
  });
  app.use(router);
  try {
    await router.push("/staff/bookings");
    app.mount({ children: [] });
    await Vue.nextTick();
    state.form.value.guests[0].fullName = "Unsaved QA resident";
    await Vue.nextTick();
    const navigation = await router.push("/staff/rooms");
    assert.equal(
      Router.isNavigationFailure(
        navigation,
        Router.NavigationFailureType.aborted,
      ),
      true,
    );
    assert.equal(router.currentRoute.value.path, "/staff/bookings");
    assert.equal(state.form.value.guests[0].fullName, "Unsaved QA resident");
    assert.equal(confirmCount, 1);
    discard = true;
    await router.push("/staff/rooms");
    assert.equal(router.currentRoute.value.path, "/staff/rooms");
    assert.equal(confirmCount, 2);
    assert.equal(
      state.form.value,
      null,
      "unmounted roster clears its sensitive fields",
    );
  } finally {
    app.unmount();
    globalThis.window = previousWindow;
  }
});
