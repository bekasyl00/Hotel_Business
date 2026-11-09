import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parse, compileScript, compileTemplate } from "@vue/compiler-sfc";
import * as Vue from "vue";
import * as Router from "vue-router";
import * as formHelpers from "../src/features/document-guests/model/form.js";

// Mount the actual component script with the real Vue router; only transport,
// translation and rendering are replaced. No guest data enters browser storage.
function documentGuestsComponent(request, capture, renderTemplate = false) {
  const { descriptor } = parse(
    readFileSync(
      new URL(
        "../src/features/document-guests/ui/DocumentGuests.vue",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  const compiled = compileScript(descriptor, {
    id: "document-guests-navigation",
  });
  const replaceImports = (source) =>
    source.replace(
      /import\s+\{([\s\S]*?)\}\s+from\s+["']([^"']+)["'];?/g,
      (_, names, path) =>
        `const {${names.replace(/\s+as\s+/g, ": ")}} = modules[${JSON.stringify(path)}];`,
    );
  const source = replaceImports(compiled.content).replace(
    "export default",
    "return",
  );
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
  component.render = renderTemplate
    ? new Function(
        "modules",
        replaceImports(
          compileTemplate({
            id: "document-guests-navigation",
            source: descriptor.template.content,
            compilerOptions: { bindingMetadata: compiled.bindings },
          }).code,
        ).replace("export function render", "return function render"),
      )({ vue: Vue })
    : () => Vue.h("div");
  return component;
}

function memoryRenderer() {
  const node = (type) => ({
    type,
    props: {},
    children: [],
    parent: null,
    addEventListener() {},
    get options() {
      return this.children.filter((child) => child.type === "option");
    },
  });
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
    setText(node, text) {
      node.text = text;
    },
    setElementText(node, text) {
      node.text = text;
    },
    patchProp(node, key, previous, next) {
      node.props[key] = next;
      if (key === "value") node.value = next;
    },
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

test("profile-backed primary contacts render as text while companion contacts stay editable", async () => {
  const previousWindow = globalThis.window;
  let state;
  globalThis.window = {
    addEventListener() {},
    removeEventListener() {},
    confirm: () => false,
  };
  const DocumentGuests = documentGuestsComponent(
    async () => ({
      bookingId: "booking-a",
      version: 1,
      expectedGuests: 2,
      buyerIndex: 0,
      primaryGuest: {
        index: 0,
        source: "profile",
        lockedFields: ["fullName", "phone"],
      },
      guests: [
        formHelpers.documentGuest({
          fullName: "Profile QA guest",
          phone: "+77000000000",
        }),
        formHelpers.documentGuest({ fullName: "Companion QA guest" }),
      ],
    }),
    (value) => {
      state = value;
    },
    true,
  );
  const router = Router.createRouter({
    history: Router.createMemoryHistory(),
    routes: [
      {
        path: "/staff/bookings",
        component: {
          render: () => Vue.h(DocumentGuests, { bookingId: "booking-a" }),
        },
      },
    ],
  });
  const app = memoryRenderer().createApp({
    render: () => Vue.h(Router.RouterView),
  });
  app.use(router);
  const root = { children: [] };
  const descendants = (node) => [node, ...node.children.flatMap(descendants)];
  try {
    await router.push("/staff/bookings");
    app.mount(root);
    await Vue.nextTick();
    const nodes = descendants(root);
    const inputs = nodes.filter((node) => node.type === "input");
    const nameInputs = inputs.filter((node) => node.props.maxlength === "160");
    assert.equal(nameInputs.length, 1);
    assert.equal(nameInputs[0].value, "Companion QA guest");
    assert.equal(inputs.filter((node) => node.props.type === "tel").length, 1);
    assert.equal(
      inputs.some((node) => node.value === "+77000000000"),
      false,
    );
    assert.equal(
      nodes.some(
        (node) => node.type === "dd" && node.text === "Profile QA guest",
      ),
      true,
    );
    assert.equal(
      nodes.some((node) => node.type === "dd" && node.text === "+77000000000"),
      true,
    );
    assert.equal(state.dirty.value, false);

    inputs.find((node) => node.props.inputmode === "numeric").value =
      "000000000000";
    state.form.value.guests[0].iin = "000000000000";
    await Vue.nextTick();
    assert.equal(state.dirty.value, true);
    assert.equal(
      state.canLeave(),
      false,
      "remaining identity edits retain the discard guard",
    );
  } finally {
    app.unmount();
    globalThis.window = previousWindow;
  }
});
