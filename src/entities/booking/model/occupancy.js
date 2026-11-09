// Calendar dates are civil dates in the property's timezone; checkout is exclusive.
export function shiftDay(day, offset) {
  return new Date(Date.parse(`${day}T00:00:00Z`) + offset * 86400000)
    .toISOString()
    .slice(0, 10);
}
export function propertyToday(timeZone = "Asia/Almaty", now = new Date()) {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone,
    calendar: "gregory",
    numberingSystem: "latn",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const values = Object.fromEntries(
    parts.map(({ type, value }) => [type, value]),
  );
  return `${values.year}-${values.month}-${values.day}`;
}
export function occupancyState(booking, now = Date.now()) {
  if (["cancelled", "rejected", "expired"].includes(booking.status))
    return "closed";
  if (booking.status === "pending")
    return booking.holdExpiresAt && Date.parse(booking.holdExpiresAt) <= now
      ? "closed"
      : "pending";
  if (booking.stayStatus === "checked_out" || booking.checkedOutAt)
    return "past";
  if (booking.stayStatus === "in_house" || booking.checkedInAt) return "active";
  return "reserved";
}
export function calendarRows(
  rooms,
  bookings,
  start,
  days,
  { query = "", state = "all", now = Date.now() } = {},
) {
  const end = shiftDay(start, days),
    search = query
      .trim()
      .replace(/^tynys-/i, "")
      .toLocaleLowerCase();
  const byRoom = new Map();
  for (const booking of bookings) {
    const status = occupancyState(booking, now);
    if (status === "closed" || booking.end <= start || booking.start >= end)
      continue;
    if (state !== "all" && status !== state) continue;
    if (!byRoom.has(booking.roomId)) byRoom.set(booking.roomId, []);
    byRoom.get(booking.roomId).push({ booking, status });
  }
  return [...rooms]
    .sort((a, b) =>
      a.number.localeCompare(b.number, undefined, { numeric: true }),
    )
    .flatMap((room) => {
      const roomMatch = `${room.number} ${room.title}`
        .toLocaleLowerCase()
        .includes(search);
      const items = (byRoom.get(room.id) || []).filter(
        ({ booking }) =>
          roomMatch ||
          `${booking.guestLabel} ${booking.id}`
            .toLocaleLowerCase()
            .includes(search),
      );
      if ((!roomMatch && !items.length) || (state !== "all" && !items.length))
        return [];
      const lanes = [];
      const bars = items
        .sort(
          (a, b) =>
            a.booking.start.localeCompare(b.booking.start) ||
            a.booking.id.localeCompare(b.booking.id),
        )
        .map(({ booking, status }) => {
          const from = Math.max(
            0,
            Math.round(
              (Date.parse(booking.start) - Date.parse(start)) / 86400000,
            ),
          );
          const until = Math.min(
            days,
            Math.round(
              (Date.parse(booking.end) - Date.parse(start)) / 86400000,
            ),
          );
          let lane = lanes.findIndex((end) => end <= from);
          if (lane === -1) lane = lanes.length;
          lanes[lane] = until;
          return { booking, status, from, span: until - from, lane };
        });
      return [{ room, bars, lanes: Math.max(1, lanes.length) }];
    });
}
