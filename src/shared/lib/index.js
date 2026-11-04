import { t, localeTag, getLocale } from "../i18n/index.js";
export const money = (value) =>
  new Intl.NumberFormat(localeTag()).format(value || 0) + " ₸";
export const dateLabel = (value) =>
  value
    ? new Intl.DateTimeFormat(localeTag(), {
        day: "numeric",
        month: getLocale() === "kk" ? "2-digit" : "short",
        year: "numeric",
        timeZone: "UTC",
      }).format(new Date(value))
    : "—";
export const timeLabel = (value) =>
  new Intl.DateTimeFormat(localeTag(), {
    day: "numeric",
    month: getLocale() === "kk" ? "2-digit" : "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Almaty",
  }).format(new Date(value));
export const asset = (name) => `/assets/${name}`;
function labels(group, keys) {
  return Object.defineProperties(
    {},
    Object.fromEntries(
      keys.map((key) => [
        key,
        { enumerable: true, get: () => t(`common.${group}.${key}`) },
      ]),
    ),
  );
}
export const categoryNames = labels("category", [
  "standard",
  "comfort",
  "suite",
]);
export const statusNames = labels("status", [
  "published",
  "draft",
  "archived",
  "active",
  "maintenance",
  "pending",
  "expired",
  "rejected",
  "confirmed",
  "cancelled",
  "disabled",
]);

export const timestampLabel = (value, timeZone = "Asia/Almaty") => {
  const timestamp = value ? new Date(value) : null;
  if (!timestamp || Number.isNaN(timestamp.getTime())) return "—";
  const options = {
    day: "numeric",
    month: getLocale() === "kk" ? "2-digit" : "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: timeZone || "Asia/Almaty",
    timeZoneName: "shortOffset",
  };
  try {
    return new Intl.DateTimeFormat(localeTag(), options).format(timestamp);
  } catch (error) {
    if (!(error instanceof RangeError)) throw error;
    return new Intl.DateTimeFormat(localeTag(), {
      ...options,
      timeZone: "Asia/Almaty",
    }).format(timestamp);
  }
};
