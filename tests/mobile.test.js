import test from "node:test";
import assert from "node:assert/strict";
import { createMobileClient } from "../src/shared/api/mobile-client.js";
const base = "https://api.example.test/api/v1";
const tokens = (n = 1) => ({
  tokenType: "Bearer",
  accessToken: `access-${n}`,
  refreshToken: `refresh-${n}`,
  expiresIn: 900,
  account: { id: "guest" },
  profile: { id: "profile" },
});
const response = (data, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
function setup(handler, initial = null, audience = "guest") {
  let saved = initial,
    time = 1000000;
  const calls = [];
  const vault = {
    read: async () => saved,
    write: async (v) => {
      saved = structuredClone(v);
    },
    clear: async () => {
      saved = null;
    },
  };
  const client = createMobileClient({
    base,
    audience,
    vault,
    now: () => time,
    fetcher: async (url, init) => {
      calls.push({ url, ...init });
      return handler(url, init);
    },
  });
  return {
    client,
    calls,
    vault,
    stored: () => saved,
    expire: () => {
      time += 900000;
    },
  };
}
const login = (c) =>
  c.request("POST", "/guest-auth/login", {
    phone: "+77000000001",
    password: "fictional-password",
  });

test("mobile login uses native endpoint, vault and bearer; never cookie/CSRF credentials", async () => {
  const x = setup((url, init) =>
    response(url.endsWith("/mobile-auth/login") ? tokens() : { ok: true }),
  );
  const result = await login(x.client);
  assert.equal(result.authenticated, true);
  assert(!("accessToken" in result));
  await x.client.request("GET", "/profile");
  assert.equal(x.calls[0].headers.Authorization, undefined);
  assert.equal(x.calls[1].headers.Authorization, "Bearer access-1");
  assert(
    x.calls.every((c) => c.credentials === "omit" && !c.headers["X-CSRFToken"]),
  );
  assert.equal(x.stored().refreshToken, "refresh-1");
});
test("simultaneous expired requests rotate refresh exactly once and replace credentials", async () => {
  let refreshes = 0;
  const x = setup((url) =>
    response(
      url.endsWith("/login")
        ? tokens()
        : url.endsWith("/refresh")
          ? (refreshes++, tokens(2))
          : { ok: true },
    ),
  );
  await login(x.client);
  x.expire();
  await Promise.all([
    x.client.request("GET", "/profile"),
    x.client.request("GET", "/my-bookings"),
  ]);
  assert.equal(refreshes, 1);
  assert.equal(x.stored().refreshToken, "refresh-2");
  assert.equal(
    x.calls.find((c) => c.url.endsWith("/refresh")).headers.Authorization,
    undefined,
  );
});
test("lost rotation response clears vault and never retries a consumed refresh token", async () => {
  const x = setup((url) => {
    if (url.endsWith("/refresh")) throw new Error("connection lost");
    return response(tokens());
  });
  await login(x.client);
  x.expire();
  await assert.rejects(x.client.request("GET", "/profile"), { status: 503 });
  assert.equal(x.stored(), null);
  await assert.rejects(x.client.request("GET", "/profile"), { status: 401 });
  assert.equal(x.calls.filter((c) => c.url.endsWith("/refresh")).length, 1);
});
test("pending rotation after app termination and credentials for another environment require login", async () => {
  for (const initial of [
    { base, pending: true },
    {
      base: "https://other.test/api/v1",
      accessToken: "a",
      refreshToken: "r",
      expiresAt: 9999999,
    },
  ]) {
    const x = setup(() => {
      throw new Error("should not request");
    }, initial);
    assert.equal(
      (await x.client.request("GET", "/guest-auth/session")).authenticated,
      false,
    );
    assert.equal(x.stored(), null);
  }
});
test("unauthenticated app can browse but cannot create anonymous cookie-owned bookings", async () => {
  const x = setup(() => response([]));
  await x.client.request("GET", "/catalog");
  await assert.rejects(x.client.request("POST", "/my-bookings", {}), {
    status: 401,
  });
  assert.equal(x.calls.length, 1);
  await assert.rejects(x.client.request("POST", "/guest-auth/register", {}), {
    code: "native_web_auth_required",
  });
});
test("logout erases credentials even when remote revocation cannot be reached", async () => {
  const x = setup((url) => {
    if (url.endsWith("/logout")) throw new Error("offline");
    return response(tokens());
  });
  await login(x.client);
  assert.equal(
    (await x.client.request("POST", "/guest-auth/logout", {})).authenticated,
    false,
  );
  assert.equal(x.stored(), null);
});
test("late protected response after logout cannot repopulate guest state", async () => {
  let release, started;
  const waiting = new Promise((r) => {
    started = r;
  });
  const x = setup((url) => {
    if (url.endsWith("/profile")) {
      started();
      return new Promise((r) => (release = r));
    }
    return response(
      url.endsWith("/login") ? tokens() : null,
      url.endsWith("/logout") ? 204 : 200,
    );
  });
  await login(x.client);
  const pending = x.client.request("GET", "/profile");
  await waiting;
  await x.client.request("POST", "/guest-auth/logout", {});
  release(response({ private: "old account" }));
  await assert.rejects(pending, { status: 401 });
  assert.equal(x.stored(), null);
});
test("mobile multipart preserves boundary and file retrieval checks content type", async () => {
  const x = setup((url) =>
    response(url.endsWith("/login") ? tokens() : { ok: true }),
  );
  await login(x.client);
  const body = new FormData();
  body.append(
    "file",
    new Blob(["fixture"], { type: "image/jpeg" }),
    "fixture.jpg",
  );
  await x.client.request("POST", "/profile/avatar", body);
  assert.equal(x.calls[1].body, body);
  assert.equal(x.calls[1].headers["Content-Type"], undefined);
  await assert.rejects(
    x.client.file("/receipts/payment/pdf", "application/pdf"),
    { status: 502 },
  );
});
test("endpoint must be HTTPS with no embedded credentials or alternate path", () => {
  for (const value of [
    "/api",
    "http://example.test/api/v1",
    "https://user:secret@example.test/api/v1",
    "https://example.test/api/v1?key=x",
  ])
    assert.throws(() => createMobileClient({ base: value, vault: {} }));
});

test("staff app uses separate auth endpoints and credential audience", async () => {
  const user = { id: "staff", role: "manager", resortId: "own-resort" };
  const x = setup(
    (url) =>
      response(
        url.endsWith("/login") || url.endsWith("/refresh")
          ? { ...tokens(), user }
          : user,
      ),
    null,
    "staff",
  );
  assert.equal(await x.client.request("GET", "/auth/session"), null);
  assert.deepEqual(
    await x.client.request("POST", "/auth/login", {
      email: "staff@example.test",
      password: "fictional-password",
    }),
    user,
  );
  assert(x.calls[0].url.endsWith("/staff-mobile-auth/login"));
  assert.equal(x.stored().audience, "staff");
  x.expire();
  await x.client.request("GET", "/workspace");
  assert(x.calls[1].url.endsWith("/staff-mobile-auth/refresh"));
  await assert.rejects(x.client.request("POST", "/guest-auth/login", {}), {
    status: 422,
  });
  const guest = setup(() => {
    throw new Error("Must not send staff credentials");
  }, x.stored());
  assert.equal(
    (await guest.client.request("GET", "/guest-auth/session")).authenticated,
    false,
  );
  assert.equal(guest.stored(), null);
});
