import test from "node:test";
import assert from "node:assert/strict";
import { whatsAppUrl, twoGisUrl } from "../src/shared/lib/catalog-contacts.js";

test("public contact links accept international phones and exact HTTPS 2GIS hosts only", () => {
  assert.equal(whatsAppUrl("+77000000001"), "https://wa.me/77000000001");
  for (const value of ["", null, 77000000001, "123", "77000000001?text=bad"]) {
    assert.equal(whatsAppUrl(value), "");
  }
  for (const value of [
    "https://2gis.kz/almaty/firm/123",
    "https://2gis.com/?m=1,2",
    "https://www.2gis.kz/",
  ]) {
    assert.equal(twoGisUrl(value), value);
  }
  for (const value of [
    "",
    null,
    "https://2gis.kz.evil.test/",
    "http://2gis.kz/",
    "https://user@2gis.kz/",
    "https://2gis.kz:444/",
    "https://2gis.kz\\@evil.test/",
    "https://2gis.kz/\npath",
  ]) {
    assert.equal(twoGisUrl(value), "");
  }
});

test("demo catalog preserves both descriptions and optional contacts, including clearing", async () => {
  const { createDemoTransport } = await import("../src/app/providers/demo.js");
  const memory = () => {
    const rows = new Map();
    return {
      getItem: (key) => rows.get(key) || null,
      setItem: (key, value) => rows.set(key, value),
      removeItem: (key) => rows.delete(key),
    };
  };
  const api = createDemoTransport({
    storage: memory(),
    session: memory(),
    delay: 0,
  });
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  const workspace = await api("GET", "/workspace");
  const original = workspace.resorts.find((item) => item.id === "altun");
  delete original.commissionPercent;
  delete original.accountId;
  const updated = await api("PATCH", "/resorts/altun", {
    ...original,
    descriptionAfter: "After the gallery",
    staffWhatsApp: "77000000001",
    twoGisUrl: "https://2gis.kz/almaty/firm/123",
  });
  delete updated.commissionPercent;
  delete updated.accountId;
  const visible = await api("GET", "/resorts/altun");
  assert.equal(visible.resort.descriptionAfter, "After the gallery");
  assert.equal(visible.resort.staffWhatsApp, "+77000000001");
  assert.deepEqual(visible.resort.media, original.media);
  await assert.rejects(
    api("PATCH", "/resorts/altun", {
      ...updated,
      twoGisUrl: "https://2gis.kz.evil.test/",
    }),
  );
  const cleared = await api("PATCH", "/resorts/altun", {
    ...updated,
    descriptionAfter: "",
    staffWhatsApp: "",
    twoGisUrl: "",
  });
  assert.equal(cleared.descriptionAfter, "");
  assert.equal(cleared.staffWhatsApp, "");
  assert.equal(cleared.description, original.description);
});
