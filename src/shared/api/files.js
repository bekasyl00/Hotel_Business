import { t, getLocale } from "../i18n/index.js";
import { errorMessage } from "./errors.js";
let fileTransport;
export function configureFileTransport(value) {
  fileTransport = value;
}
export async function requestFile(
  path,
  base = "/api",
  expectedType = "application/pdf",
) {
  if (fileTransport) return fileTransport(path, expectedType);
  let response;
  try {
    response = await fetch(`${base.replace(/\/$/, "")}${path}`, {
      credentials: "include",
      cache: "no-store",
      headers: { "Accept-Language": getLocale() },
    });
  } catch {
    throw new Error(t("common.error.fileNetwork"));
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw Object.assign(
      new Error(errorMessage(data?.message, response.status, data?.code)),
      { status: response.status },
    );
  }
  if (
    expectedType &&
    !response.headers.get("Content-Type")?.includes(expectedType)
  )
    throw new Error(t("common.error.fileType"));
  return response.blob();
}
export async function requestAsset(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(t("common.error.font"));
  return response.arrayBuffer();
}
