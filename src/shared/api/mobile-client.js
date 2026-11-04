// Transport-independent token rotation. The vault must be OS-protected on devices.
export function createMobileClient({
  base,
  audience = "guest",
  vault,
  fetcher = fetch,
  now = Date.now,
  locale = () => "ru",
  onLocalLogout = () => {},
}) {
  if (!["guest", "staff"].includes(audience))
    throw new Error("Invalid native audience");
  const auth = audience === "staff" ? "/auth" : "/guest-auth";
  const nativeAuth =
    audience === "staff" ? "/staff-mobile-auth" : "/mobile-auth";
  const signedOut =
    audience === "staff"
      ? null
      : { authenticated: false, account: null, profile: null };
  const origin = new URL(base);
  if (
    origin.protocol !== "https:" ||
    origin.username ||
    origin.password ||
    origin.search ||
    origin.hash ||
    origin.pathname !== "/api/v1"
  )
    throw new Error("Mobile API requires an HTTPS /api/v1 endpoint");
  let credentials = null,
    loaded = false,
    generation = 0,
    queue = Promise.resolve();
  const problem = (status, code, message) =>
    Object.assign(new Error(message || code), { status, code });
  const exclusive = (fn) => {
    const next = queue.then(fn, fn);
    queue = next.catch(() => {});
    return next;
  };
  async function load() {
    if (loaded) return;
    const value = await vault.read();
    if (
      value?.base === base &&
      (value.audience || "guest") === audience &&
      !value.pending &&
      value.accessToken &&
      value.refreshToken &&
      Number.isFinite(value.expiresAt)
    )
      credentials = value;
    else if (value) await vault.clear();
    loaded = true;
  }
  async function clear() {
    generation++;
    credentials = null;
    loaded = true;
    await vault.clear();
  }
  async function raw(method, path, body, token) {
    if (
      !/^\/[a-z0-9][^\\]*$/i.test(path) ||
      path.includes("..") ||
      /[\r\n#]/.test(path)
    )
      throw problem(422, "invalid_request");
    const multipart =
      typeof FormData !== "undefined" && body instanceof FormData;
    try {
      return await fetcher(`${base}${path}`, {
        method,
        credentials: "omit",
        cache: "no-store",
        headers: {
          "Accept-Language": locale(),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(body !== undefined && !multipart
            ? { "Content-Type": "application/json" }
            : {}),
        },
        body:
          body === undefined
            ? undefined
            : multipart
              ? body
              : JSON.stringify(body),
      });
    } catch {
      throw problem(503, "network_error");
    }
  }
  async function json(response) {
    if (response.status === 204) return null;
    const data = await response.json().catch(() => null);
    if (!response.ok) throw problem(response.status, data?.code, data?.message);
    if (data === null) throw problem(502, "invalid_response");
    return data;
  }
  async function persist(data) {
    if (
      data?.tokenType !== "Bearer" ||
      !data.accessToken ||
      !data.refreshToken ||
      !(data.expiresIn > 0)
    )
      throw problem(502, "invalid_response");
    const next = {
      base,
      audience,
      accessToken: data.accessToken,
      refreshToken: data.refreshToken,
      expiresAt: now() + data.expiresIn * 1000,
    };
    await vault.write(next);
    credentials = next;
    loaded = true;
  }
  async function rotate() {
    const previous = credentials;
    credentials = null;
    // Persist the uncertain state before consuming a one-use refresh credential.
    // A crash, lost response or write failure requires login, never a refresh retry.
    await vault.write({ base, audience, pending: true });
    try {
      await persist(
        await json(
          await raw("POST", `${nativeAuth}/refresh`, {
            refreshToken: previous.refreshToken,
          }),
        ),
      );
    } catch (error) {
      await clear();
      throw error;
    }
  }
  async function access(staleToken) {
    return exclusive(async () => {
      await load();
      if (!credentials) return null;
      if (
        credentials.expiresAt <= now() + 30000 ||
        (staleToken && credentials.accessToken === staleToken)
      )
        await rotate();
      return credentials?.accessToken;
    });
  }
  async function send(method, path, body) {
    const current = generation;
    let token = await access();
    if (current !== generation) throw problem(401, "invalid_token");
    const publicRead =
      method === "GET" &&
      /^\/(categories|catalog|resorts|rooms|availability|reviews|media\/files)(\/|\?|$)/.test(
        path,
      );
    if (!token && !publicRead) throw problem(401, "invalid_token");
    let response = await raw(method, path, body, token);
    if (current !== generation) throw problem(401, "invalid_token");
    if (response.status === 401 && token) {
      token = await access(token);
      if (current !== generation) throw problem(401, "invalid_token");
      if (!token) throw problem(401, "invalid_token");
      response = await raw(method, path, body, token);
      if (current !== generation) throw problem(401, "invalid_token");
      if (response.status === 401)
        await exclusive(async () => {
          if (current === generation) await clear();
        });
    }
    return response;
  }
  return {
    origin: origin.origin,
    async request(method, path, body) {
      if (path === `${auth}/login` && method === "POST")
        return exclusive(async () => {
          await clear();
          const result = await json(
            await raw("POST", `${nativeAuth}/login`, {
              ...body,
              deviceName:
                audience === "staff"
                  ? "Тыныс Команда · iPhone"
                  : "Тыныс · iPhone",
            }),
          );
          await persist(result);
          if (audience === "staff") return result.user;
          return {
            authenticated: true,
            account: result.account,
            profile: result.profile,
          };
        });
      if (path === `${auth}/logout` && method === "POST")
        return exclusive(async () => {
          await load();
          try {
            if (credentials) {
              if (credentials.expiresAt <= now() + 30000) await rotate();
              await json(
                await raw(
                  "POST",
                  `${nativeAuth}/logout`,
                  {},
                  credentials.accessToken,
                ),
              );
            }
          } catch {
            onLocalLogout();
          } finally {
            await clear();
          }
          return signedOut;
        });
      if (path === `${auth}/session`) {
        if (!(await access())) return signedOut;
      } else if (
        path.startsWith(`${auth}/`) ||
        (audience === "staff" && path.startsWith("/guest-auth/"))
      )
        throw problem(422, "native_web_auth_required");
      return json(await send(method, path, body));
    },
    async file(path, expectedType) {
      const response = await send("GET", path);
      if (!response.ok) await json(response);
      if (
        expectedType &&
        !response.headers.get("Content-Type")?.includes(expectedType)
      )
        throw problem(502, "invalid_response");
      return response.blob();
    },
  };
}
