export function holdSeconds(expiresAt, now = Date.now()) {
  const expires = Date.parse(expiresAt || "");
  return Number.isFinite(expires)
    ? Math.max(0, Math.ceil((expires - now) / 1000))
    : null;
}
export function holdLabel(seconds) {
  if (seconds === null) return "—";
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
