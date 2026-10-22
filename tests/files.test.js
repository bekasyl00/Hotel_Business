import test from "node:test";
import assert from "node:assert/strict";
import { requestFile } from "../src/shared/api/files.js";

test("private receipt PDF uses session cookies, no cache and configured API base", async () => {
  const original = globalThis.fetch;
  let seen;
  globalThis.fetch = async (url, options) => {
    seen = { url, options };
    return new Response("%PDF-1.4", {
      headers: { "Content-Type": "application/pdf" },
    });
  };
  try {
    const file = await requestFile("/receipts/example/pdf", "/api/");
    assert.equal(await file.text(), "%PDF-1.4");
    assert.equal(seen.url, "/api/receipts/example/pdf");
    assert.equal(seen.options.credentials, "include");
    assert.equal(seen.options.cache, "no-store");
  } finally {
    globalThis.fetch = original;
  }
});

test("PDF boundary preserves permission failures and rejects HTML/network errors", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () =>
      Response.json({ message: "Private receipt" }, { status: 404 });
    await assert.rejects(
      requestFile("/receipts/foreign/pdf"),
      (e) => e.status === 404 && e.message === "Private receipt",
    );
    globalThis.fetch = async () =>
      new Response("<html>Login</html>", {
        headers: { "Content-Type": "text/html" },
      });
    await assert.rejects(
      requestFile("/receipts/example/pdf"),
      /неподдерживаемом формате/,
    );
    globalThis.fetch = async () => {
      throw new TypeError("offline");
    };
    await assert.rejects(
      requestFile("/receipts/example/pdf"),
      /Проверьте соединение/,
    );
  } finally {
    globalThis.fetch = original;
  }
});
