import { createMobileClient } from "@/shared/api/mobile-client.js";
import { ApiError, configureFileTransport } from "@/shared/api";
import { nativeVault, isNative, nativeSessionNotice } from "@/shared/native";
import { getLocale } from "@/shared/i18n";

export function createMobileTransport(base, audience = "guest") {
  // A preview in a normal browser must never silently persist native credentials.
  if (!isNative())
    throw new Error("Native API mode requires the installed iOS app");
  const client = createMobileClient({
    base,
    audience,
    vault: nativeVault,
    locale: getLocale,
    onLocalLogout: () => {
      nativeSessionNotice.value = "common.mobile.localLogout";
    },
  });
  const previews = new Map(),
    originals = new Map();
  const wrap = async (action) => {
    try {
      return await action();
    } catch (error) {
      throw new ApiError(error.message, error.status || 503, {}, error.code);
    }
  };
  configureFileTransport((path, expectedType) =>
    wrap(() => client.file(path, expectedType)),
  );
  let previewGeneration = 0;
  function dispose() {
    previewGeneration++;
    for (const url of originals.keys()) URL.revokeObjectURL(url);
    previews.clear();
    originals.clear();
  }
  async function preview(path, type = "image/") {
    const run = previewGeneration;
    if (!previews.has(path))
      previews.set(
        path,
        client
          .file(path.replace(/^\/api(?:\/v1)?/, ""), type)
          .then((blob) => {
            if (run !== previewGeneration) throw new ApiError("", 401);
            const url = URL.createObjectURL(blob);
            originals.set(url, path);
            return url;
          })
          .catch((error) => {
            if (run === previewGeneration) previews.delete(path);
            throw error;
          }),
      );
    return previews.get(path);
  }
  async function hydrate(value, key = "") {
    if (Array.isArray(value))
      return Promise.all(value.map((item) => hydrate(item, key)));
    if (value && typeof value === "object")
      return Object.fromEntries(
        await Promise.all(
          Object.entries(value).map(async ([k, v]) => [k, await hydrate(v, k)]),
        ),
      );
    if (typeof value !== "string") return value;
    if (/^\/api\/media\/files\//.test(value)) {
      if (key === "avatarUrl" || audience === "staff")
        return preview(value, null).catch(() => "");
      return `${client.origin}${value}`;
    }
    return value;
  }
  function canonical(value) {
    if (typeof FormData !== "undefined" && value instanceof FormData)
      return value;
    if (Array.isArray(value)) return value.map(canonical);
    if (value && typeof value === "object")
      return Object.fromEntries(
        Object.entries(value).map(([k, v]) => [k, canonical(v)]),
      );
    if (typeof value === "string") {
      if (originals.has(value)) return originals.get(value);
      if (value.startsWith(`${client.origin}/api/media/files/`))
        return value.slice(client.origin.length);
    }
    return value;
  }
  return (method, path, body) =>
    wrap(async () => {
      if (
        [
          "/guest-auth/logout",
          "/guest-auth/login",
          "/auth/logout",
          "/auth/login",
        ].includes(path)
      )
        dispose();
      const value = await client.request(method, path, canonical(body));
      if (path === "/media" && value?.url && value.kind === "image")
        return { ...value, url: await preview(value.url) };
      return hydrate(value);
    });
}
