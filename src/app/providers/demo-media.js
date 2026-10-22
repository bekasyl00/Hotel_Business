import {
  ApiError,
  uploadErrorCode,
  IMAGE_TYPES,
} from "../../shared/api/index.js";
import { ownerOf } from "./demo-guest-auth.js";

const PREFIX = "/media/demo/";
const MAX_BYTES = 100 * 1024 * 1024;
const MAX_AGE = 24 * 60 * 60 * 1000;
const fail = (code, status = 422) => {
  throw new ApiError(null, status, {}, code);
};
const assetId = (value) =>
  typeof value === "string" && /^\/media\/demo\/[0-9a-f-]{36}$/.test(value)
    ? value.slice(PREFIX.length)
    : null;

export function createIndexedMediaRepository(indexedDB = globalThis.indexedDB) {
  let connection;
  async function database() {
    if (!indexedDB) fail("media_storage_unavailable", 503);
    connection ||= new Promise((resolve, reject) => {
      const opening = indexedDB.open("tynys:media:v1", 1);
      opening.onupgradeneeded = () =>
        opening.result.createObjectStore("files", { keyPath: "id" });
      opening.onsuccess = () => {
        opening.result.onversionchange = () => {
          opening.result.close();
          connection = undefined;
        };
        resolve(opening.result);
      };
      opening.onerror = () => reject(opening.error);
      opening.onblocked = () => reject(new Error("Media database is blocked"));
    }).catch(() => {
      connection = undefined;
      fail("media_storage_unavailable", 503);
    });
    return connection;
  }
  async function operation(mode, action) {
    const db = await database();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction("files", mode);
      const result = action(transaction.objectStore("files"));
      transaction.oncomplete = () => resolve(result.result);
      transaction.onabort = transaction.onerror = () =>
        reject(transaction.error || result.error);
    }).catch((error) =>
      fail(
        error?.name === "QuotaExceededError"
          ? "media_quota"
          : "media_storage_unavailable",
        503,
      ),
    );
  }
  return {
    get: (id) => operation("readonly", (store) => store.get(id)),
    list: () => operation("readonly", (store) => store.getAll()),
    put: (record) => operation("readwrite", (store) => store.put(record)),
    remove: (id) => operation("readwrite", (store) => store.delete(id)),
  };
}

export function createDemoMediaStore({
  repository = createIndexedMediaRepository(),
  createObjectURL = (blob) => URL.createObjectURL(blob),
  revokeObjectURL = (url) => URL.revokeObjectURL(url),
} = {}) {
  const urls = new Map(),
    reverse = new Map(),
    pending = new Map();
  const forget = (id) => {
    if (!urls.has(id)) return;
    const url = urls.get(id);
    revokeObjectURL(url);
    reverse.delete(url);
    urls.delete(id);
  };
  const canonical = (value) => {
    if (typeof value === "string") return reverse.get(value) || value;
    if (Array.isArray(value)) return value.map(canonical);
    if (value && typeof value === "object" && !(value instanceof FormData))
      return Object.fromEntries(
        Object.entries(value).map(([key, entry]) => [key, canonical(entry)]),
      );
    return value;
  };
  const references = (value) => {
    const ids = new Set();
    function visit(entry) {
      const id = assetId(entry);
      if (id) ids.add(id);
      else if (entry && typeof entry === "object")
        Object.values(entry).forEach(visit);
    }
    visit(value);
    return ids;
  };
  const hydrate = async (value) => {
    const id = assetId(value);
    if (id) {
      if (!urls.has(id)) {
        if (!pending.has(id))
          pending.set(
            id,
            (async () => {
              const record = await repository.get(id);
              if (!record) return;
              const url = createObjectURL(record.file);
              urls.set(id, url);
              reverse.set(url, `${PREFIX}${id}`);
            })().finally(() => pending.delete(id)),
          );
        await pending.get(id);
      }
      return urls.get(id) || "";
    }
    if (Array.isArray(value)) return Promise.all(value.map(hydrate));
    if (value && typeof value === "object")
      return Object.fromEntries(
        await Promise.all(
          Object.entries(value).map(async ([key, entry]) => [
            key,
            await hydrate(entry),
          ]),
        ),
      );
    return value;
  };
  async function validateReferences(value, permitted) {
    for (const id of references(canonical(value))) {
      const record = await repository.get(id);
      if (!record || !permitted(record)) fail("media_not_found", 404);
    }
  }
  async function save(file, metadata, db) {
    const error = uploadErrorCode(file, {
      allowVideo: metadata.purpose === "catalog",
    });
    if (error) fail(error);
    const bytes = new Uint8Array(await file.slice(0, 16).arrayBuffer());
    const text = (start, end) =>
      String.fromCharCode(...bytes.slice(start, end));
    const signatures = {
      "image/jpeg": bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff,
      "image/png": text(1, 4) === "PNG" && bytes[0] === 0x89,
      "image/webp": text(0, 4) === "RIFF" && text(8, 12) === "WEBP",
      "video/mp4": text(4, 8) === "ftyp",
      "video/webm":
        bytes[0] === 0x1a &&
        bytes[1] === 0x45 &&
        bytes[2] === 0xdf &&
        bytes[3] === 0xa3,
    };
    if (!signatures[file.type]) fail("media_invalid");
    const retained = references({
      resorts: db.resorts,
      rooms: db.rooms,
      reviews: db.reviews,
      profiles: db.guestProfiles,
    });
    let total = 0;
    for (const record of await repository.list()) {
      if (!retained.has(record.id) && Date.now() - record.createdAt > MAX_AGE) {
        await repository.remove(record.id);
        forget(record.id);
      } else total += record.file.size;
    }
    if (total + file.size > MAX_BYTES) fail("media_quota", 503);
    const id = crypto.randomUUID();
    await repository.put({ id, file, ...metadata, createdAt: Date.now() });
    return {
      id,
      url: `${PREFIX}${id}`,
      kind: IMAGE_TYPES.includes(file.type) ? "image" : "video",
      alt: "",
    };
  }
  async function remove(reference) {
    const id = assetId(canonical(reference));
    if (!id) return;
    await repository.remove(id);
    forget(id);
  }
  const dispose = () => [...urls.keys()].forEach(forget);
  return { canonical, hydrate, save, remove, validateReferences, dispose };
}

export async function demoMediaRequest({
  db,
  user,
  method,
  pathname,
  payload,
  authorize,
  commit,
  media,
}) {
  const done = (value) => ({ handled: true, value });
  if (pathname === "/profile/avatar" && ["POST", "DELETE"].includes(method)) {
    if (!db.guestAccount) fail("media_avatar_account", 401);
    const profile = db.guestProfiles.find(
      (entry) => entry.owner === ownerOf(db),
    );
    const before = { ...profile };
    const upload =
      method === "POST"
        ? await media.save(
            payload.get?.("file"),
            { purpose: "avatar", owner: ownerOf(db) },
            db,
          )
        : null;
    Object.assign(profile, {
      avatarUrl: upload?.url || "",
      version: profile.version + 1,
      updatedAt: new Date().toISOString(),
    });
    try {
      commit("profiles", profile, before, "avatar");
    } catch (error) {
      if (upload) await media.remove(upload.url).catch(() => {});
      throw error;
    }
    // Once the new reference is committed, cleanup must not turn success into failure.
    if (before.avatarUrl) await media.remove(before.avatarUrl).catch(() => {});
    const { owner, ...publicProfile } = profile;
    return done({ profile: publicProfile });
  }
  if (pathname === "/media" && method === "POST") {
    const bookingId = payload.get?.("bookingId");
    let metadata;
    if (bookingId) {
      if (user) fail("media_not_found", 403);
      const booking = db.bookings.find(
        (entry) =>
          entry.id === bookingId &&
          entry.source === "website" &&
          entry.ownerId === ownerOf(db),
      );
      if (
        !booking ||
        booking.status !== "confirmed" ||
        Date.parse(`${booking.end}T00:00:00+05:00`) > Date.now()
      )
        fail("media_not_found", 403);
      if (db.reviews.some((review) => review.bookingId === bookingId))
        fail("media_not_found", 409);
      metadata = {
        purpose: "review",
        owner: ownerOf(db),
        bookingId,
        resortId: booking.resortId,
      };
    } else {
      const resortId = payload.get?.("resortId");
      authorize(resortId);
      if (
        !db.resorts.some(
          (entry) => entry.id === resortId && entry.status !== "archived",
        )
      )
        fail("media_not_found", 404);
      metadata = { purpose: "catalog", resortId };
    }
    return done(await media.save(payload.get?.("file"), metadata, db));
  }
  if (["POST", "PATCH"].includes(method)) {
    const catalog = pathname.match(/^\/(resorts|rooms)(?:\/([^/]+))?$/);
    if (catalog && payload.media) {
      const item = db[catalog[1]].find((entry) => entry.id === catalog[2]);
      const resortId =
        catalog[1] === "resorts"
          ? item?.id
          : payload.resortId || item?.resortId;
      await media.validateReferences(
        payload.media,
        (record) =>
          record.purpose === "catalog" && record.resortId === resortId,
      );
    }
    if (pathname === "/reviews" && payload.photos)
      await media.validateReferences(
        payload.photos,
        (record) =>
          record.purpose === "review" &&
          record.bookingId === payload.bookingId &&
          record.owner === ownerOf(db),
      );
  }
  return { handled: false };
}
