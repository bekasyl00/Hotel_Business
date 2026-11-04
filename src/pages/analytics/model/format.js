export const metricOptions = [
  {
    key: "bookingCount",
    labelKey: "requests",
    unit: "count",
    descriptionKey: "requestsDescription",
  },
  {
    key: "grossReceived",
    labelKey: "grossReceived",
    unit: "money",
    descriptionKey: "grossDescription",
  },
  {
    key: "refunds",
    labelKey: "refunds",
    unit: "money",
    descriptionKey: "refundsDescription",
  },
  {
    key: "netReceived",
    labelKey: "netReceived",
    unit: "money",
    descriptionKey: "netDescription",
  },
  {
    key: "reviewCount",
    labelKey: "reviews",
    unit: "count",
    descriptionKey: "reviewsDescription",
  },
];
export function csvCell(value) {
  let text = String(value ?? "");
  if (typeof value === "string" && /^(?:\s*[=+\-@]|[\t\r\n])/.test(text))
    text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
export function comparison(current, previous, options = {}) {
  const {
    locale = "ru-KZ",
    unchanged = "Без изменений",
    noBaseline = "Нет базы для сравнения",
  } = options;
  if (previous === 0) return current === 0 ? unchanged : noBaseline;
  const change = ((current - previous) / Math.abs(previous)) * 100;
  return `${change > 0 ? "+" : ""}${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(change)}%`;
}

export function reportDateAfter(days = 0, now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Almaty",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const part = (type) => parts.find((value) => value.type === type).value;
  const result = new Date(
    Date.UTC(
      Number(part("year")),
      Number(part("month")) - 1,
      Number(part("day")) + days,
    ),
  );
  return result.toISOString().slice(0, 10);
}
