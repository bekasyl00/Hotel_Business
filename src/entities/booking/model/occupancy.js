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
export function placeLabel(position) {
  let n = Math.max(1, Math.trunc(Number(position) || 1));
  const chars = [];
  while (n > 0) {
    n -= 1;
    chars.push(String.fromCharCode(97 + (n % 26)));
    n = Math.trunc(n / 26);
  }
  return chars.reverse().join("");
}
export function roomPlaces(room) {
  if (Array.isArray(room?.places) && room.places.length) {
    return [...room.places]
      .sort((a, b) => (a.position || 0) - (b.position || 0))
      .map((p, idx) => {
        const position = p.position || idx + 1;
        const label = p.label || placeLabel(position);
        return {
          id: p.id || `${room.id}-p${position}`,
          position,
          label,
          unitLabel: p.unitLabel || `${room.number}${label}`,
          status: p.status || "active",
        };
      });
  }
  const count = Math.max(1, Math.trunc(Number(room?.capacity) || 1));
  return Array.from({ length: count }, (_, idx) => {
    const position = idx + 1;
    const label = placeLabel(position);
    return {
      id: `${room?.id || "room"}-p${position}`,
      position,
      label,
      unitLabel: `${room?.number || ""}${label}`,
      status: room?.status === "maintenance" ? "maintenance" : "active",
    };
  });
}
export function calendarRoomGroups(
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
      const places = roomPlaces(room);
      const placeSearchText = places.map((p) => p.unitLabel).join(" ");
      const roomMatch = `${room.number} ${room.title} ${placeSearchText}`
        .toLocaleLowerCase()
        .includes(search);
      const items = (byRoom.get(room.id) || [])
        .filter(
          ({ booking }) =>
            roomMatch ||
            `${booking.guestLabel} ${booking.id} ${(booking.placeLabels || []).join(" ")}`
              .toLocaleLowerCase()
              .includes(search),
        )
        .sort(
          (a, b) =>
            a.booking.start.localeCompare(b.booking.start) ||
            a.booking.id.localeCompare(b.booking.id),
        );
      if ((!roomMatch && !items.length) || (state !== "all" && !items.length))
        return [];

      const activePlaces = places.filter((p) => p.status === "active");
      const candidatePlaces = activePlaces.length ? activePlaces : places;
      const byPlaceId = new Map(places.map((p) => [p.id, []]));
      const byUnitLabel = new Map(
        places.map((p) => [p.unitLabel.toLocaleLowerCase(), p.id]),
      );

      for (const entry of items) {
        const { booking, status } = entry;
        const from = Math.max(
          0,
          Math.round(
            (Date.parse(booking.start) - Date.parse(start)) / 86400000,
          ),
        );
        const until = Math.min(
          days,
          Math.round((Date.parse(booking.end) - Date.parse(start)) / 86400000),
        );
        const span = Math.max(1, until - from);

        let targetIds = [];
        if (Array.isArray(booking.placeIds) && booking.placeIds.length) {
          targetIds = booking.placeIds.filter((id) => byPlaceId.has(id));
        }
        if (
          !targetIds.length &&
          Array.isArray(booking.placeLabels) &&
          booking.placeLabels.length
        ) {
          targetIds = booking.placeLabels
            .map((lbl) => byUnitLabel.get(String(lbl).toLocaleLowerCase()))
            .filter(Boolean);
        }
        if (!targetIds.length) {
          const needed = Math.max(
            1,
            Math.min(Number(booking.guests) || 1, candidatePlaces.length),
          );
          const free = candidatePlaces.filter((p) => {
            const existing = byPlaceId.get(p.id) || [];
            return !existing.some(
              (b) =>
                b.booking.start < booking.end && booking.start < b.booking.end,
            );
          });
          const chosen = free.slice(0, needed);
          if (chosen.length < needed) {
            const used = new Set(chosen.map((p) => p.id));
            for (const p of candidatePlaces) {
              if (!used.has(p.id)) {
                chosen.push(p);
                if (chosen.length === needed) break;
              }
            }
          }
          targetIds = chosen.map((p) => p.id);
        }
        const resolvedLabels = targetIds
          .map((id) => places.find((p) => p.id === id)?.unitLabel)
          .filter(Boolean);
        for (const pid of targetIds) {
          byPlaceId.get(pid)?.push({
            booking,
            status,
            from,
            until,
            span,
            placeLabels: booking.placeLabels?.length
              ? booking.placeLabels
              : resolvedLabels,
          });
        }
      }

      const placeRows = places.map((place) => {
        const rawBars = byPlaceId.get(place.id) || [];
        const placeLanes = [];
        const occupiedSet = new Set();
        const bars = rawBars.map((item) => {
          let lane = placeLanes.findIndex((endIdx) => endIdx <= item.from);
          if (lane === -1) lane = placeLanes.length;
          placeLanes[lane] = item.until;
          if (item.status !== "past") {
            for (let i = item.from; i < item.until; i += 1) {
              occupiedSet.add(shiftDay(start, i));
            }
          }
          return {
            booking: item.booking,
            status: item.status,
            from: item.from,
            span: item.span,
            lane,
            placeLabels: item.placeLabels,
          };
        });
        return {
          room,
          place,
          bars,
          lanes: Math.max(1, placeLanes.length),
          occupiedSet,
        };
      });

      const roomLanes = [];
      const roomBars = items.map(({ booking, status }) => {
        const from = Math.max(
          0,
          Math.round(
            (Date.parse(booking.start) - Date.parse(start)) / 86400000,
          ),
        );
        const until = Math.min(
          days,
          Math.round((Date.parse(booking.end) - Date.parse(start)) / 86400000),
        );
        let lane = roomLanes.findIndex((end) => end <= from);
        if (lane === -1) lane = roomLanes.length;
        roomLanes[lane] = until;
        return { booking, status, from, span: until - from, lane };
      });
      return [
        {
          room,
          places: placeRows,
          rows: placeRows,
          bars: roomBars,
          lanes: Math.max(1, roomLanes.length),
        },
      ];
    });
}
export function calendarRows(rooms, bookings, start, days, options = {}) {
  return calendarRoomGroups(rooms, bookings, start, days, options);
}
