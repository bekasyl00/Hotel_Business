import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createPinia, setActivePinia } from "pinia";
import { configureTransport } from "../src/shared/api/index.js";
const apiUrl = new URL("../src/shared/api/index.js", import.meta.url).href;
const source = (
  await readFile(
    new URL("../src/entities/guest-account/model/store.js", import.meta.url),
    "utf8",
  )
)
  .replace('"pinia"', JSON.stringify(import.meta.resolve("pinia")))
  .replace('"@/shared/api"', JSON.stringify(apiUrl));
const { useGuestAccountStore } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);

test("a late anonymous restore cannot overwrite successful guest login", async () => {
  setActivePinia(createPinia());
  let finish,
    reads = 0;
  configureTransport((method) =>
    method === "GET"
      ? (reads++,
        new Promise((resolve) => {
          finish = resolve;
        }))
      : Promise.resolve({ authenticated: true, account: { id: "fictional" } }),
  );
  const store = useGuestAccountStore();
  const first = store.restore(),
    second = store.restore();
  assert.equal(reads, 1);
  await store.login({});
  finish({ authenticated: false });
  await Promise.all([first, second]);
  assert.equal(store.authenticated, true);
  assert.equal(store.session.account.id, "fictional");
});
test("network failure does not silently log a guest out", async () => {
  setActivePinia(createPinia());
  const store = useGuestAccountStore();
  store.session = { authenticated: true };
  store.ready = true;
  configureTransport(() => Promise.reject(new Error("offline")));
  await assert.rejects(store.restore(), /offline/);
  assert.equal(store.authenticated, true);
});
test("a restore started before logout cannot reinstate the old session", async () => {
  setActivePinia(createPinia());
  let finish;
  configureTransport((method) =>
    method === "GET"
      ? new Promise((resolve) => {
          finish = resolve;
        })
      : Promise.resolve({ authenticated: false }),
  );
  const store = useGuestAccountStore(),
    pending = store.restore();
  await store.logout();
  finish({ authenticated: true });
  await pending;
  assert.equal(store.authenticated, false);
});
test("a restore begun during login cannot overwrite the completed login", async () => {
  setActivePinia(createPinia());
  let finishLogin, finishRestore;
  configureTransport(
    (method) =>
      new Promise((resolve) => {
        if (method === "GET") finishRestore = resolve;
        else finishLogin = resolve;
      }),
  );
  const store = useGuestAccountStore();
  const login = store.login({}),
    restore = store.restore();
  finishLogin({ authenticated: true });
  await login;
  finishRestore({ authenticated: false });
  await restore;
  assert.equal(store.authenticated, true);
});
