import test from "node:test";
import assert from "node:assert/strict";
import { createHttpTransport } from "../src/shared/api/index.js";
test("media upload preserves FormData and CSRF without overriding browser multipart boundary", async () => {
  const original = globalThis.fetch;
  const body = new FormData();
  body.append("file", new Blob(["test image"]), "test.jpg");
  let upload;
  globalThis.fetch = async (url, options) => {
    if (url.endsWith("/auth/csrf"))
      return Response.json({ token: "media-csrf" });
    upload = options;
    return Response.json({ url: "/media/test.jpg" });
  };
  try {
    await createHttpTransport()("POST", "/media", body);
    assert.equal(upload.body, body);
    assert.equal(upload.headers["Content-Type"], undefined);
    assert.equal(upload.headers["X-CSRFToken"], "media-csrf");
    assert.equal(upload.credentials, "include");
  } finally {
    globalThis.fetch = original;
  }
});
test("HTTP adapter sends cookies and JSON, preserves server conflicts and handles network errors", async () => {
  const original = globalThis.fetch;
  try {
    let observed;
    globalThis.fetch = async (url, options) => {
      if (url.endsWith("/auth/csrf"))
        return Response.json({ token: "csrf-test" });
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
    assert.equal(observed.options.headers["X-CSRFToken"], "csrf-test");
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

test("HTTP adapter accepts anonymous sessions and refreshes CSRF after login", async () => {
  const original = globalThis.fetch;
  const seen = [];
  let csrfCalls = 0;
  globalThis.fetch = async (url, options) => {
    if (url.endsWith("/auth/csrf"))
      return Response.json({ token: `csrf-${++csrfCalls}` });
    seen.push(options.headers["X-CSRFToken"]);
    if (url.endsWith("/auth/session"))
      return new Response(null, { status: 204 });
    return Response.json({ id: "staff" });
  };
  try {
    const api = createHttpTransport("/api");
    assert.equal(await api("GET", "/auth/session"), null);
    await api("POST", "/auth/login", {
      email: "test@example.test",
      password: "test",
    });
    await api("PATCH", "/rooms/1", { version: 1 });
    assert.equal(csrfCalls, 2);
    assert.deepEqual(seen, [undefined, "csrf-1", "csrf-2"]);
  } finally {
    globalThis.fetch = original;
  }
});

test("HTTP requests and CSRF bypass browser caches without retrying financial writes", async () => {
  const original = globalThis.fetch;
  const seen = [];
  globalThis.fetch = async (url, options) => {
    seen.push({ url, options });
    if (url.endsWith("/auth/csrf"))
      return Response.json({ token: "csrf-cache-test" });
    if (url.endsWith("/payments")) throw new TypeError("ambiguous disconnect");
    return Response.json({ account: null });
  };
  try {
    const api = createHttpTransport();
    await api("GET", "/guest-auth/session");
    await api("GET", "/availability");
    await assert.rejects(
      api("POST", "/payments", { bookingId: "fictional" }),
      (error) => error.status === 503,
    );
    assert.ok(seen.every(({ options }) => options.cache === "no-store"));
    assert.equal(seen.filter(({ url }) => url.endsWith("/payments")).length, 1);
    assert.equal(seen.length, 4);
  } finally {
    globalThis.fetch = original;
  }
});

test("rate limits expose server retry delay without replaying the request", async () => {
  const original = globalThis.fetch;
  let calls = 0;
  let delay = "23";
  globalThis.fetch = async () => {
    calls++;
    return Response.json(
      { code: "rate_limited" },
      { status: 429, headers: { "Retry-After": delay } },
    );
  };
  try {
    const api = createHttpTransport();
    await assert.rejects(
      api("GET", "/availability"),
      (error) => error.status === 429 && error.retryAfter === 23,
    );
    assert.equal(calls, 1);
    delay = "-5";
    await assert.rejects(
      api("GET", "/availability"),
      (error) => error.retryAfter === undefined,
    );
    assert.equal(calls, 2);
  } finally {
    globalThis.fetch = original;
  }
});
