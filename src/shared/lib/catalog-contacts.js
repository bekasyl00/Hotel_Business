export function whatsAppUrl(value) {
  return typeof value === "string" && /^\+?[1-9][0-9]{7,14}$/.test(value)
    ? `https://wa.me/${value.replace(/^\+/, "")}`
    : "";
}

export function twoGisUrl(value) {
  if (typeof value !== "string" || /[\x00-\x1f\\]/.test(value)) return "";
  try {
    const url = new URL(value);
    return url.protocol === "https:" &&
      ["2gis.kz", "2gis.com", "www.2gis.kz", "www.2gis.com"].includes(
        url.hostname,
      ) &&
      !url.username &&
      !url.password &&
      (!url.port || url.port === "443")
      ? value
      : "";
  } catch {
    return "";
  }
}
