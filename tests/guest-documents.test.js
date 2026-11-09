import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { compileScript, parse } from "@vue/compiler-sfc";
import * as Vue from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { publicRoutes } from "../src/app/routes-public.js";
import { routes as combinedRoutes } from "../src/app/routes-combined.js";
import { i18n } from "../src/shared/i18n/index.js";

function substituteImports(source) {
  return source
    .replace(
      /import\s+\{([\s\S]*?)\}\s+from\s+["']([^"']+)["'];?/g,
      (_, names, path) =>
        `const {${names.replace(/\s+as\s+/g, ": ")}} = modules[${JSON.stringify(path)}];`,
    )
    .replace("export default", "return");
}
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
};
const flush = async () => {
  await new Promise((resolve) => setImmediate(resolve));
  await Vue.nextTick();
};

function mountDocuments({
  request,
  authenticated = true,
  demo = false,
  restore,
} = {}) {
  const previousWindow = globalThis.window,
    previousDocument = globalThis.document;
  const window = new EventTarget(),
    document = new EventTarget();
  document.visibilityState = "visible";
  globalThis.window = window;
  globalThis.document = document;
  const calls = [],
    redirects = [],
    filePaths = [];
  const account = {
    authenticated,
    revision: 0,
    restore: restore || (async () => {}),
    clear() {
      this.authenticated = false;
      this.revision++;
    },
  };
  const { descriptor } = parse(
    readFileSync(
      new URL(
        "../src/widgets/guest-documents/ui/GuestDocuments.vue",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  const source = substituteImports(
    compileScript(descriptor, {
      id: "guest-documents-behavior",
      inlineTemplate: true,
    }).content,
  );
  const component = new Function("modules", source)({
    vue: Vue,
    "vue-router": {
      useRouter: () => ({ replace: async (target) => redirects.push(target) }),
    },
    "vue-i18n": { useI18n: () => ({ t: i18n.global.t }) },
    "@/entities/guest-account": { useGuestAccountStore: () => account },
    "@/shared/ui": {
      DocumentFiles: {
        props: ["path", "number"],
        setup(props) {
          filePaths.push(props.path);
          return () => Vue.h("button", {}, props.number);
        },
      },
    },
    "@/shared/api": {
      request: async (...args) => {
        calls.push(args);
        return request ? request(...args) : [];
      },
    },
    "@/shared/lib": { dateLabel: (value) => value?.slice(0, 10) },
    "@/shared/config": { isDemo: demo },
  });
  const node = (tag = "", text = "") => ({
    tag,
    text,
    children: [],
    parent: null,
    props: {},
  });
  const remove = (child) => {
    if (child.parent)
      child.parent.children.splice(child.parent.children.indexOf(child), 1);
    child.parent = null;
  };
  const renderer = Vue.createRenderer({
    createElement: (tag) => node(tag),
    createText: (value) => node("#text", value),
    createComment: () => node("#comment"),
    insert(child, parent, anchor) {
      remove(child);
      child.parent = parent;
      const index = anchor ? parent.children.indexOf(anchor) : -1;
      parent.children.splice(
        index < 0 ? parent.children.length : index,
        0,
        child,
      );
    },
    remove,
    parentNode: (child) => child.parent,
    nextSibling: (child) =>
      child.parent?.children[child.parent.children.indexOf(child) + 1] || null,
    setText: (child, value) => {
      child.text = value;
    },
    setElementText: (child, value) => {
      child.text = value;
      child.children = [];
    },
    patchProp: (child, key, _, value) => {
      child.props[key] = value;
    },
  });
  const root = node("root"),
    app = renderer.createApp(component);
  app.mount(root);
  const text = (entry = root) =>
    [entry.text, ...entry.children.map(text)].join(" ");
  const find = (predicate, entry = root) =>
    predicate(entry)
      ? entry
      : entry.children.map((child) => find(predicate, child)).find(Boolean);
  return {
    calls,
    redirects,
    filePaths,
    account,
    window,
    document,
    text,
    button: (label) =>
      find((entry) => entry.tag === "button" && text(entry).trim() === label),
    close() {
      app.unmount();
      globalThis.window = previousWindow;
      globalThis.document = previousDocument;
    },
  };
}

test("guest documents shows pending, genuine empty and newly released records on refresh", async () => {
  const first = deferred(),
    second = deferred();
  let attempt = 0;
  const view = mountDocuments({
    request: () => (++attempt === 1 ? first.promise : second.promise),
  });
  try {
    assert.match(view.text(), /Загружаем документы/);
    assert.doesNotMatch(view.text(), /Документов пока нет/);
    await flush();
    assert.deepEqual(view.calls, [["GET", "/my-documents"]]);
    first.resolve([]);
    await flush();
    assert.match(view.text(), /Документов пока нет/);
    assert.match(view.text(), /после выезда/);
    view.button("Обновить").props.onClick();
    view.button("Обновить").props.onClick();
    await flush();
    assert.equal(view.calls.length, 2);
    assert.equal(view.button("Обновить").props.disabled, true);
    second.resolve([
      {
        id: "owned-document",
        number: "ACT-FIXTURE",
        kind: "act",
        resortName: "Fixture property",
        start: "2030-01-01",
        end: "2030-01-03",
        releasedAt: "2030-01-03T12:00:00Z",
      },
    ]);
    await flush();
    assert.match(view.text(), /Fixture property/);
    assert.match(view.text(), /2030-01-01/);
    assert.doesNotMatch(view.text(), /Документов пока нет/);
    assert.deepEqual(view.filePaths, ["/my-documents/owned-document"]);
  } finally {
    view.close();
  }
});

test("list failure has retry instead of empty state and a retry can recover", async () => {
  let fail = true;
  const view = mountDocuments({
    request: async () => {
      if (fail) throw new Error("offline");
      return [];
    },
  });
  try {
    await flush();
    assert.match(view.text(), /Не удалось загрузить документы/);
    assert.doesNotMatch(view.text(), /Документов пока нет/);
    fail = false;
    view.button("Повторить").props.onClick();
    await flush();
    assert.match(view.text(), /Документов пока нет/);
    assert.doesNotMatch(view.text(), /Не удалось загрузить/);
  } finally {
    view.close();
  }
});

test("document reads require guest login and expired sessions return to login with a safe next path", async () => {
  for (const authenticated of [false, true]) {
    const view = mountDocuments({
      authenticated,
      request: async () => {
        throw Object.assign(new Error("expired"), { status: 401 });
      },
    });
    try {
      await flush();
      assert.equal(view.calls.length, authenticated ? 1 : 0);
      assert.deepEqual(view.redirects, [
        { path: "/account/login", query: { next: "/documents" } },
      ]);
      assert.equal(view.account.authenticated, false);
      assert.deepEqual(view.filePaths, []);
    } finally {
      view.close();
    }
  }
});

test("returning to the visible app refreshes documents and disposal ignores pending responses", async () => {
  const pending = deferred();
  let attempt = 0;
  const view = mountDocuments({
    request: async () => (++attempt === 1 ? [] : pending.promise),
  });
  await flush();
  view.document.visibilityState = "hidden";
  view.window.dispatchEvent(new Event("focus"));
  await flush();
  assert.equal(view.calls.length, 1);
  view.document.visibilityState = "visible";
  view.document.dispatchEvent(new Event("visibilitychange"));
  await flush();
  assert.equal(view.calls.length, 2);
  view.close();
  pending.resolve([{ id: "late", kind: "act", number: "ACT-LATE" }]);
  await flush();
  assert.deepEqual(view.filePaths, []);
  view.window.dispatchEvent(new Event("focus"));
  assert.equal(view.calls.length, 2);
});

test("demo documents distinguishes unsupported demo issuance from an empty real account", async () => {
  const view = mountDocuments({ demo: true });
  try {
    await flush();
    assert.equal(view.calls.length, 0);
    assert.match(view.text(), /В деморежиме они не выдаются/);
    assert.doesNotMatch(view.text(), /Документов пока нет/);
  } finally {
    view.close();
  }
});

test("public/mobile and combined routes expose documents as a guest-only page", async () => {
  for (const routes of [publicRoutes, combinedRoutes]) {
    const router = createRouter({ history: createMemoryHistory(), routes });
    const target = router.resolve("/documents");
    assert.equal(target.matched.length, 1);
    assert.equal(target.meta.guest, true);
    assert.equal(target.meta.staff, undefined);
  }
  let guard;
  const guest = { authenticated: false, restore: async () => {} };
  const failed = { value: false };
  const source = substituteImports(
    readFileSync(new URL("../src/app/router.js", import.meta.url), "utf8"),
  );
  new Function("modules", source)({
    vue: Vue,
    "vue-router": {
      createWebHistory: () => ({}),
      createRouter: () => ({
        beforeEach: (callback) => {
          guard = callback;
        },
        onError() {},
      }),
    },
    "@/entities/session": {
      useSessionStore: () => {
        throw new Error("must not use staff identity");
      },
    },
    "@/entities/guest-account": { useGuestAccountStore: () => guest },
    "@/shared/config": {
      appSurface: "public",
      isMobile: false,
      isStaffApp: false,
    },
    "@/shared/i18n": { t: i18n.global.t },
    "#surface-routes": { routes: publicRoutes },
    "./route-errors.js": { routeLoadFailed: failed },
  });
  const target = {
    path: "/documents",
    fullPath: "/documents",
    meta: { guest: true },
  };
  assert.deepEqual(await guard(target), {
    path: "/account/login",
    query: { next: "/documents" },
  });
  guest.authenticated = true;
  assert.equal(await guard(target), undefined);
  guest.restore = async () => {
    throw new Error("offline");
  };
  assert.equal(await guard(target), false);
  assert.equal(failed.value, true);
});
