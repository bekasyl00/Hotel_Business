import test from "node:test";
import assert from "node:assert/strict";
import {
  createDemoTransport,
  DATABASE_KEY,
} from "../src/app/providers/demo.js";
import {
  createDemoMediaStore,
  createIndexedMediaRepository,
} from "../src/app/providers/demo-media.js";
import { uploadErrorCode } from "../src/shared/api/index.js";

function memory() {
  const records = new Map();
  return {
    getItem: (key) => records.get(key) || null,
    setItem: (key, value) => records.set(key, value),
    removeItem: (key) => records.delete(key),
  };
}
function setup() {
  const storage = memory(),
    files = new Map(),
    revoked = [];
  let serial = 0;
  const repository = {
    get: async (id) => files.get(id),
    list: async () => [...files.values()],
    put: async (record) => files.set(record.id, record),
    remove: async (id) => files.delete(id),
  };
  const device = (session = memory()) => {
    const media = createDemoMediaStore({
      repository,
      createObjectURL: () => `blob:demo-${++serial}`,
      revokeObjectURL: (url) => revoked.push(url),
    });
    return {
      api: createDemoTransport({ storage, session, delay: 0, media }),
      session,
      media,
    };
  };
  return { ...device(), device, files, revoked, storage, repository };
}
const image = () =>
  new File(
    [new Uint8Array([0x89, 0x50, 0x4e, 0x47, 13, 10, 26, 10])],
    "fictional.png",
    { type: "image/png" },
  );
function form(file = image(), fields = {}) {
  const value = new FormData();
  value.append("file", file);
  for (const [key, entry] of Object.entries(fields)) value.append(key, entry);
  return value;
}
async function register(api) {
  const challenge = await api("POST", "/guest-auth/challenges", {
    purpose: "register",
    phone: "+77000000093",
  });
  await api("POST", "/guest-auth/register", {
    challengeId: challenge.challengeId,
    code: challenge.demoCode,
    password: "Fictional-test-password!2026",
    name: "Media demo",
  });
}

test("file limits distinguish photo and video and reject unsupported or empty files", () => {
  assert.equal(uploadErrorCode(image()), null);
  assert.equal(
    uploadErrorCode({ type: "image/png", size: 8 * 1024 * 1024 + 1 }),
    "media_image_size",
  );
  assert.equal(
    uploadErrorCode({ type: "video/mp4", size: 100 }),
    "media_image_required",
  );
  assert.equal(
    uploadErrorCode(
      { type: "video/mp4", size: 40 * 1024 * 1024 + 1 },
      { allowVideo: true },
    ),
    "media_video_size",
  );
  assert.equal(
    uploadErrorCode({ type: "image/svg+xml", size: 100 }),
    "media_image_required",
  );
  assert.equal(
    uploadErrorCode({ type: "image/png", size: 0 }),
    "media_invalid",
  );
});

test("catalog upload persists Blob separately, round-trips edits and hydrates after reload", async () => {
  const { api, files, storage, device, session, revoked } = setup();
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  const uploaded = await api(
    "POST",
    "/media",
    form(image(), { resortId: "altun" }),
  );
  assert.match(uploaded.url, /^blob:/);
  assert.equal(files.get(uploaded.id).file.type, "image/png");
  const room = (await api("GET", "/workspace")).rooms[0];
  const saved = await api("PATCH", `/rooms/${room.id}`, {
    ...room,
    media: [{ ...uploaded, alt: "Fictional" }],
  });
  assert.equal(saved.media[0].url, uploaded.url);
  const raw = storage.getItem(DATABASE_KEY);
  assert.ok(raw.includes(`/media/demo/${uploaded.id}`));
  assert.ok(!raw.includes("blob:"));
  assert.ok(!raw.includes("data:image"));
  api.dispose();
  assert.deepEqual(revoked, [uploaded.url]);
  const reloaded = device(session);
  const after = (await reloaded.api("GET", "/workspace")).rooms.find(
    (entry) => entry.id === room.id,
  );
  assert.match(after.media[0].url, /^blob:/);
  assert.notEqual(after.media[0].url, uploaded.url);
  assert.equal(after.media[0].alt, "Fictional");
});

test("avatar requires account, replacing/deleting removes old Blob and logout hides photo", async () => {
  const { api, files } = setup();
  await assert.rejects(
    api("POST", "/profile/avatar", form()),
    (error) => error.status === 401,
  );
  await register(api);
  const first = await api("POST", "/profile/avatar", form());
  assert.match(first.profile.avatarUrl, /^blob:/);
  assert.equal(
    (await api("GET", "/guest-auth/session")).profile.avatarUrl,
    first.profile.avatarUrl,
  );
  const second = await api("POST", "/profile/avatar", form());
  assert.notEqual(second.profile.avatarUrl, first.profile.avatarUrl);
  assert.equal(files.size, 1);
  await api("POST", "/guest-auth/logout", {});
  assert.equal((await api("GET", "/profile")).profile.avatarUrl, "");
  await api("POST", "/guest-auth/login", {
    phone: "+77000000093",
    password: "Fictional-test-password!2026",
  });
  assert.equal(
    (await api("GET", "/profile")).profile.avatarUrl,
    second.profile.avatarUrl,
  );
  const removed = await api("DELETE", "/profile/avatar");
  assert.equal(removed.profile.avatarUrl, "");
  assert.equal(files.size, 0);
});

test("upload rejects spoofed content and foreign tenant references", async () => {
  const { api } = setup();
  await api("POST", "/auth/login", { accountId: "manager-altun" });
  await assert.rejects(
    api("POST", "/media", form(image(), { resortId: "arasan" })),
    (error) => error.status === 403,
  );
  await assert.rejects(
    api(
      "POST",
      "/media",
      form(new File(["not a photo"], "fake.png", { type: "image/png" }), {
        resortId: "altun",
      }),
    ),
    (error) => error.code === "media_invalid",
  );
  const uploaded = await api(
    "POST",
    "/media",
    form(image(), { resortId: "altun" }),
  );
  await api("POST", "/auth/login", { accountId: "admin" });
  const foreign = (await api("GET", "/workspace")).rooms.find(
    (room) => room.resortId === "arasan",
  );
  await assert.rejects(
    api("PATCH", `/rooms/${foreign.id}`, { ...foreign, media: [uploaded] }),
    (error) => error.status === 404,
  );
});

test("failed metadata persistence rolls back new avatar Blob and retains existing photo", async () => {
  const { api, storage, files } = setup();
  await register(api);
  const original = (await api("POST", "/profile/avatar", form())).profile
    .avatarUrl;
  const persist = storage.setItem;
  storage.setItem = () => {
    throw new Error("quota");
  };
  await assert.rejects(
    api("POST", "/profile/avatar", form()),
    (error) => error.status === 503,
  );
  storage.setItem = persist;
  assert.equal(files.size, 1);
  assert.equal((await api("GET", "/profile")).profile.avatarUrl, original);
});

test("media cache deduplicates concurrent references and missing files do not break catalog", async () => {
  const { media, api, files } = setup();
  await api("POST", "/auth/login", { accountId: "admin" });
  const upload = await api(
    "POST",
    "/media",
    form(image(), { resortId: "altun" }),
  );
  const reference = media.canonical(upload.url);
  media.dispose();
  const values = await media.hydrate([
    reference,
    reference,
    { url: reference },
  ]);
  assert.equal(values[0], values[1]);
  assert.equal(values[0], values[2].url);
  media.dispose();
  files.clear();
  assert.equal(await media.hydrate(reference), "");
});

test("unavailable IndexedDB produces explicit storage error without claiming successful upload", async () => {
  const repository = createIndexedMediaRepository(undefined);
  await assert.rejects(
    repository.get("test"),
    (error) => error.code === "media_storage_unavailable",
  );
});

test("review photos belong to the completed stay and cannot be reused for another booking", async () => {
  const { api, storage } = setup();
  await api("GET", "/profile");
  const db = JSON.parse(storage.getItem(DATABASE_KEY));
  db.bookings.push(
    ...["first", "second"].map((id) => ({
      id,
      ownerId: db.clientId,
      source: "website",
      resortId: "altun",
      status: "confirmed",
      start: "2020-01-01",
      end: "2020-01-02",
      createdAt: "2020-01-01T00:00:00Z",
    })),
  );
  storage.setItem(DATABASE_KEY, JSON.stringify(db));
  const photo = await api(
    "POST",
    "/media",
    form(image(), { bookingId: "first" }),
  );
  await assert.rejects(
    api("POST", "/reviews", {
      bookingId: "second",
      rating: 5,
      text: "Fictional stay review",
      photos: [photo.url],
    }),
    (error) => error.status === 404,
  );
  const review = await api("POST", "/reviews", {
    bookingId: "first",
    rating: 5,
    text: "Fictional stay review",
    photos: [photo.url],
  });
  assert.equal(review.photos[0], photo.url);
  await assert.rejects(
    api("POST", "/media", form(image(), { bookingId: "first" })),
    (error) => error.status === 409,
  );
});

test("demo storage quota fails before saving a new file", async () => {
  const { api, files } = setup();
  await api("POST", "/auth/login", { accountId: "admin" });
  files.set("large-fixture", {
    id: "large-fixture",
    file: { size: 100 * 1024 * 1024 },
    createdAt: Date.now(),
  });
  await assert.rejects(
    api("POST", "/media", form(image(), { resortId: "altun" })),
    (error) => error.code === "media_quota",
  );
  assert.equal(files.size, 1);
});
