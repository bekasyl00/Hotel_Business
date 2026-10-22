import { errorMessage } from "./errors.js";
import { getLocale } from "../i18n/index.js";
export class ApiError extends Error {
  constructor(message, status = 400, fields = {}, code = null) {
    super(errorMessage(message, status, code));
    this.status = status;
    this.fields = fields;
    this.code = code;
  }
}
let transport;
export const configureTransport = (value) => {
  transport = value;
};
export const request = (method, path, body) => {
  if (!transport) throw new Error("API transport is not configured");
  return transport(method, path, body);
};
export function createHttpTransport(base = "/api") {
  let csrfToken;
  return async (method, path, body) => {
    let response;
    const multipart =
      typeof FormData !== "undefined" && body instanceof FormData;
    try {
      if (!["GET", "HEAD"].includes(method) && !csrfToken) {
        const csrf = await fetch(`${base.replace(/\/$/, "")}/auth/csrf`, {
          credentials: "include",
        });
        const data = await csrf.json();
        if (!csrf.ok || !data.token)
          throw new ApiError(
            "Не удалось защитить запрос. Обновите страницу.",
            csrf.status || 503,
          );
        csrfToken = data.token;
      }
      response = await fetch(`${base.replace(/\/$/, "")}${path}`, {
        method,
        credentials: "include",
        headers: {
          "Accept-Language": getLocale(),
          ...(multipart ? {} : { "Content-Type": "application/json" }),
          ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
        },
        body:
          body === undefined
            ? undefined
            : multipart
              ? body
              : JSON.stringify(body),
      });
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(
        "Нет соединения с сервером. Проверьте сеть и повторите.",
        503,
      );
    }
    if (
      [
        "/auth/login",
        "/auth/logout",
        "/guest-auth/login",
        "/guest-auth/register",
        "/guest-auth/reset",
        "/guest-auth/logout",
      ].includes(path) ||
      response.status === 403
    )
      csrfToken = undefined;
    if (response.status === 204) return null;
    const invalid = Symbol();
    const data = await response.json().catch(() => invalid);
    if (!response.ok)
      throw new ApiError(
        data?.message,
        response.status,
        data?.fields,
        data?.code,
      );
    if (data === invalid)
      throw new ApiError("Сервер вернул некорректный ответ.", 502);
    return data;
  };
}

export { requestFile, requestAsset } from "./files.js";
