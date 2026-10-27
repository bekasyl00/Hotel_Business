import { ApiError } from "../../shared/api/index.js";
export const GUEST_SESSION_KEY = "tynys:guest-session:v1";
const SCOPE_KEY = "tynys:guest-challenge:v1";
const ANONYMOUS_KEY = "tynys:guest-anonymous:v1";
const fail = (code, status = 422) => {
  throw new ApiError("Проверьте данные и повторите.", status, {}, code);
};
const copy = (value) => JSON.parse(JSON.stringify(value));
export const ownerOf = (db) => db.viewerId || db.clientId;
export function serializeDemo(db) {
  const { viewerId, guestAccount, ...stored } = db;
  return JSON.stringify(stored);
}
export function resolveGuest(db, session) {
  db.guestAccounts ||= [];
  db.guestChallenges ||= [];
  db.guestAttempts ||= [];
  let identity;
  try {
    identity = JSON.parse(session.getItem(GUEST_SESSION_KEY) || "null");
  } catch {
    identity = null;
  }
  const account =
    identity &&
    db.guestAccounts.find(
      (a) => a.id === identity.id && a.authVersion === identity.version,
    );
  if (identity && !account) {
    session.removeItem(GUEST_SESSION_KEY);
    session.setItem(ANONYMOUS_KEY, crypto.randomUUID());
  }
  db.guestAccount = account || null;
  db.viewerId = account?.owner || session.getItem(ANONYMOUS_KEY) || db.clientId;
}
export function normalizePhone(value) {
  if (typeof value !== "string" || value.length > 32) fail("phone_invalid");
  let phone = value.replace(/[\s()-]/g, "");
  if (/^8\d{10}$/.test(phone)) phone = "+7" + phone.slice(1);
  if (!/^\+77\d{9}$/.test(phone)) fail("phone_invalid");
  return phone;
}
function password(value) {
  if (
    typeof value !== "string" ||
    value.length < 12 ||
    value.length > 128 ||
    /^\d+$/.test(value) ||
    /^(password|qwerty|123456|пароль)/i.test(value)
  )
    fail("weak_password");
  return value;
}
async function digest(value) {
  const bytes = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value),
  );
  return Array.from(new Uint8Array(bytes), (x) =>
    x.toString(16).padStart(2, "0"),
  ).join("");
}
async function passwordHash(value, salt) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(value),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const bytes = await crypto.subtle.deriveBits(
    {
      name: "PBKDF2",
      hash: "SHA-256",
      salt: new TextEncoder().encode(salt),
      iterations: 100000,
    },
    key,
    256,
  );
  return Array.from(new Uint8Array(bytes), (x) =>
    x.toString(16).padStart(2, "0"),
  ).join("");
}
function scope(session) {
  let value = session.getItem(SCOPE_KEY);
  if (!value) {
    value = crypto.randomUUID();
    session.setItem(SCOPE_KEY, value);
  }
  return value;
}
function sessionData(db) {
  const account = db.guestAccount;
  const profile =
    account && db.guestProfiles.find((p) => p.owner === account.owner);
  const publicProfile = profile && {
    id: profile.id,
    name: profile.name,
    phone: profile.phone,
    avatarUrl: profile.avatarUrl || "",
    version: profile.version,
    createdAt: profile.createdAt,
    updatedAt: profile.updatedAt,
  };
  return {
    authenticated: !!account,
    account: account ? { id: account.id, phone: account.phone } : null,
    profile: publicProfile || null,
    mode: "demo",
  };
}
export async function demoAuthRequest({
  db,
  session,
  method,
  pathname,
  payload,
  persist,
  now = Date.now(),
}) {
  if (!pathname.startsWith("/guest-auth/")) return { handled: false };
  const done = (value) => ({ handled: true, value: copy(value) });
  const endpoint = pathname.slice("/guest-auth/".length);
  if (endpoint === "session" && method === "GET") return done(sessionData(db));
  if (method !== "POST") fail("method_not_allowed", 405);
  const establish = (account) => {
    session.setItem(ANONYMOUS_KEY, crypto.randomUUID());
    session.setItem(
      GUEST_SESSION_KEY,
      JSON.stringify({ id: account.id, version: account.authVersion }),
    );
    session.removeItem(SCOPE_KEY);
    db.guestAccount = account;
    db.viewerId = account.owner;
    return done(sessionData(db));
  };
  if (endpoint === "logout") {
    session.setItem(ANONYMOUS_KEY, crypto.randomUUID());
    session.removeItem(GUEST_SESSION_KEY);
    session.removeItem(SCOPE_KEY);
    resolveGuest(db, session);
    return done(sessionData(db));
  }
  if (endpoint === "challenges" || endpoint === "login") {
    const phone = normalizePhone(payload.phone),
      since = now - 15 * 60000;
    db.guestAttempts = db.guestAttempts.filter((a) => a.at > since);
    if (
      db.guestAttempts.filter(
        (a) => a.phone === phone && a.endpoint === endpoint,
      ).length >= 10 ||
      db.guestAttempts.length >= 50
    )
      fail("rate_limited", 429);
    db.guestAttempts.push({ phone, endpoint, at: now });
    persist();
    if (endpoint === "login") {
      const account = db.guestAccounts.find((a) => a.phone === phone);
      if (typeof payload.password !== "string" || payload.password.length > 128)
        fail("invalid_credentials", 401);
      const hash = await passwordHash(
        payload.password,
        account?.salt || "unknown-account",
      );
      if (!account || hash !== account.passwordHash)
        fail("invalid_credentials", 401);
      return establish(account);
    }
    if (!["register", "reset"].includes(payload.purpose))
      fail("invalid_request");
    const recent = db.guestChallenges.find(
      (c) =>
        c.phone === phone &&
        c.purpose === payload.purpose &&
        c.createdAt > now - 60000,
    );
    if (recent) fail("resend_cooldown", 429);
    db.guestChallenges = db.guestChallenges.filter(
      (c) =>
        c.expiresAt > now &&
        !(c.phone === phone && c.purpose === payload.purpose),
    );
    const id = crypto.randomUUID(),
      code = String(
        crypto.getRandomValues(new Uint32Array(1))[0] % 1000000,
      ).padStart(6, "0");
    const challenge = {
      id,
      phone,
      purpose: payload.purpose,
      scope: scope(session),
      hash: await digest(id + code),
      createdAt: now,
      expiresAt: now + 300000,
      attempts: 0,
      used: false,
    };
    db.guestChallenges.push(challenge);
    persist();
    return done({
      challengeId: id,
      expiresAt: new Date(challenge.expiresAt).toISOString(),
      retryAfterSeconds: 60,
      mode: "demo",
      demoCode: code,
    });
  }
  if (!["register", "reset"].includes(endpoint)) fail("not_found", 404);
  const pass = password(payload.password);
  if (
    endpoint === "register" &&
    (typeof payload.name !== "string" ||
      !payload.name.trim() ||
      payload.name.trim().length > 80)
  )
    fail("name_invalid");
  const c = db.guestChallenges.find(
    (c) =>
      c.id === payload.challengeId &&
      c.scope === session.getItem(SCOPE_KEY) &&
      c.purpose === endpoint,
  );
  if (!c || c.used || c.attempts >= 5) fail("invalid_code");
  if (c.expiresAt <= now) fail("code_expired");
  c.attempts++;
  persist();
  if (
    typeof payload.code !== "string" ||
    !/^\d{6}$/.test(payload.code) ||
    (await digest(c.id + payload.code)) !== c.hash
  )
    fail("invalid_code");
  c.used = true;
  const existing = db.guestAccounts.find((a) => a.phone === c.phone);
  if (endpoint === "reset") {
    if (existing) {
      existing.salt = crypto.randomUUID();
      existing.passwordHash = await passwordHash(pass, existing.salt);
      existing.authVersion++;
    }
    persist();
    resolveGuest(db, session);
    session.removeItem(SCOPE_KEY);
    return done({ ok: true, mode: "demo" });
  }
  if (existing || db.guestAccount) {
    persist();
    fail("registration_failed");
  }
  const previous = ownerOf(db),
    owner = crypto.randomUUID(),
    at = new Date(now).toISOString();
  let profile = db.guestProfiles.find((p) => p.owner === previous);
  if (!profile) {
    profile = { id: crypto.randomUUID(), owner, version: 1, createdAt: at };
    db.guestProfiles.push(profile);
  }
  Object.assign(profile, {
    owner,
    name: payload.name.trim(),
    phone: c.phone,
    updatedAt: at,
    version: profile.version + 1,
  });
  for (const b of db.bookings)
    if (b.source === "website" && b.ownerId === previous) {
      b.ownerId = owner;
      b.guestProfileId = profile.id;
    }
  const salt = crypto.randomUUID(),
    account = {
      id: crypto.randomUUID(),
      owner,
      phone: c.phone,
      salt,
      passwordHash: await passwordHash(pass, salt),
      authVersion: 1,
    };
  db.guestAccounts.push(account);
  persist();
  return establish(account);
}
