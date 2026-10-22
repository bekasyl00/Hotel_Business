export class ApiError extends Error {
  constructor(message, status = 400, fields = {}) {
    super(message);
    this.status = status;
    this.fields = fields;
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
  return async (method, path, body) => {
    let response;
    try {
      response = await fetch(`${base.replace(/\/$/, "")}${path}`, {
        method,
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError(
        "Нет соединения с сервером. Проверьте сеть и повторите.",
        503,
      );
    }
    if (response.status === 204) return null;
    const data = await response.json().catch(() => null);
    if (!response.ok)
      throw new ApiError(
        data?.message || "Не удалось выполнить запрос.",
        response.status,
        data?.fields,
      );
    if (data === null)
      throw new ApiError("Сервер вернул некорректный ответ.", 502);
    return data;
  };
}
