import test from "node:test";
import assert from "node:assert/strict";
import { createHttpTransport } from "../src/shared/api/index.js";
test("HTTP adapter sends cookies and JSON, preserves server conflicts and handles network errors", async () => {
  const original = globalThis.fetch;
  try {
    let observed;
    globalThis.fetch = async (url, options) => {
      observed = { url, options };
      return new Response(JSON.stringify({ id: "created" }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
    };
    const api = createHttpTransport("/api/");
    assert.deepEqual(await api("POST", "/rooms", { number: "201" }), {
      id: "created",
    });
    assert.equal(observed.url, "/api/rooms");
    assert.equal(observed.options.credentials, "include");
    assert.deepEqual(JSON.parse(observed.options.body), { number: "201" });
    globalThis.fetch = async () =>
      new Response(
        JSON.stringify({ message: "Conflict", fields: { version: "Stale" } }),
        { status: 409 },
      );
    await assert.rejects(
      api("PATCH", "/rooms/1", {}),
      (e) => e.status === 409 && e.fields.version === "Stale",
    );
    globalThis.fetch = async () => new Response(null, { status: 204 });
    assert.equal(await api("POST", "/auth/logout"), null);
    globalThis.fetch = async () => {
      throw new TypeError("offline");
    };
    await assert.rejects(api("GET", "/catalog"), (e) => e.status === 503);
  } finally {
    globalThis.fetch = original;
  }
});
