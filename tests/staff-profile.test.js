import test from "node:test";
import assert from "node:assert/strict";
import {
  createDemoTransport,
  DATABASE_KEY,
} from "../src/app/providers/demo.js";
function memory() {
  const data = new Map();
  return {
    getItem: (key) => data.get(key) || null,
    setItem: (key, value) => data.set(key, value),
    removeItem: (key) => data.delete(key),
  };
}
async function setup() {
  const storage = memory(),
    session = memory(),
    api = createDemoTransport({ storage, session, delay: 0 });
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  return { api, storage };
}
test("staff demo profile edits only personal fields and preserves sign-in permissions", async () => {
  const { api, storage } = await setup();
  const before = await api("GET", "/staff-profile");
  assert.deepEqual(
    before.resorts.map((r) => r.id),
    ["altun"],
  );
  const body = {
    version: before.profile.version,
    accountVersion: before.profile.accountVersion,
    name: "Fictional Employee",
    jobTitle: "Reception",
    contactPhone: "+7 (700) 000-00-00",
  };
  const updated = await api("PATCH", "/staff-profile", body);
  assert.equal(updated.profile.version, 2);
  assert.equal(updated.profile.contactPhone, "+77000000000");
  assert.equal(updated.account.role, "manager");
  assert.equal(updated.account.login, before.profile.login);
  assert.equal((await api("GET", "/auth/session")).name, "Fictional Employee");
  await assert.rejects(
    api("PATCH", "/staff-profile", body),
    (e) => e.status === 409,
  );
  const audit = JSON.parse(storage.getItem(DATABASE_KEY)).audit.find(
    (e) => e.entity === "staffProfile",
  );
  assert.equal(JSON.stringify(audit.after).includes("77000000000"), false);
  for (const forbidden of [
    { role: "admin" },
    { login: "fake@example.test" },
    { iin: "000000000000" },
  ])
    await assert.rejects(
      api("PATCH", "/staff-profile", { ...body, version: 2, ...forbidden }),
      (e) => e.status === 422,
    );
  await api("POST", "/auth/logout");
  await assert.rejects(api("GET", "/staff-profile"), (e) => e.status === 401);
});
test("an admin cannot silently overwrite a freshly changed self profile", async () => {
  const { api } = await setup();
  const { profile } = await api("GET", "/staff-profile");
  await api("PATCH", "/staff-profile", {
    version: profile.version,
    accountVersion: profile.accountVersion,
    name: "Updated Employee",
    jobTitle: "",
    contactPhone: "",
  });
  await api("POST", "/auth/login", { accountId: "admin" });
  const account = (await api("GET", "/workspace")).accounts.find(
    (a) => a.id === "manager-altun",
  );
  await assert.rejects(
    api("PATCH", "/accounts/manager-altun", {
      ...account,
      profileVersion: 1,
      name: "Stale employee",
    }),
    (e) => e.status === 409,
  );
  const { profileVersion: ignored, ...legacyAccount } = account;
  await assert.rejects(
    api("PATCH", "/accounts/manager-altun", {
      ...legacyAccount,
      name: "Stale employee",
    }),
    (e) => e.status === 409,
  );
  assert.equal(
    (
      await api("PATCH", "/accounts/manager-altun", {
        ...account,
        name: "Corrected employee",
      })
    ).profileVersion,
    3,
  );
});

test("legacy account edits without a name change may omit profile version", async () => {
  const { api } = await setup();
  await api("POST", "/auth/login", { accountId: "admin" });
  const account = (await api("GET", "/workspace")).accounts.find(
    (a) => a.id === "manager-altun",
  );
  const { profileVersion: ignored, ...legacyAccount } = account;
  const changed = await api("PATCH", "/accounts/manager-altun", {
    ...legacyAccount,
    login: "updated@example.test",
  });
  assert.equal(changed.login, "updated@example.test");
  assert.equal(changed.profileVersion, account.profileVersion || 1);
});
