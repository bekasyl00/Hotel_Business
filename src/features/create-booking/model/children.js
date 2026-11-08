function parts(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return null;
  const [year, month, day] = value.split("-").map(Number);
  const d = new Date(Date.UTC(year, month - 1, day));
  return d.getUTCFullYear() === year &&
    d.getUTCMonth() === month - 1 &&
    d.getUTCDate() === day
    ? [year, month, day]
    : null;
}
export function ageAt(birth, checkin) {
  const b = parts(birth),
    c = parts(checkin);
  if (!b || !c || birth > checkin) return null;
  return c[0] - b[0] - (c[1] < b[1] || (c[1] === b[1] && c[2] < b[2]) ? 1 : 0);
}
export function birthHint(prefix, checkin) {
  if (!/^\d{6}$/.test(prefix || "") || !parts(checkin)) return "";
  const year = Number(checkin.slice(0, 4)),
    yy = Number(prefix.slice(0, 2));
  const candidates = [
    Math.floor(year / 100) * 100 + yy,
    Math.floor(year / 100) * 100 + yy - 100,
  ];
  return (
    candidates
      .map((y) => `${y}-${prefix.slice(2, 4)}-${prefix.slice(4, 6)}`)
      .find((date) => {
        const age = ageAt(date, checkin);
        return age !== null && age >= 0 && age < 14;
      }) || ""
  );
}

export function childBirthFromIin(value, checkin, today) {
  if (!/^[0-9]{12}$/.test(value || "")) return "";
  const birth = birthHint(value.slice(0, 6), checkin);
  return birth && birth <= today ? birth : "";
}

export function selectChildCount(value, guests, maxGuests = 4) {
  if (value === "" || !Number.isInteger(Number(value))) return null;
  if (!Number.isInteger(maxGuests) || maxGuests < 1) return null;
  const children = Number(value);
  if (children < 0 || children >= maxGuests) return null;
  const currentGuests = Number.isInteger(Number(guests)) ? Number(guests) : 1;
  return {
    children,
    guests: Math.max(currentGuests, children + 1),
  };
}

export function roomForParty(rooms, currentId, guests) {
  if (!Number.isInteger(guests) || guests < 1 || guests > 4) return null;
  const current = rooms.find((room) => room.id === currentId);
  if (current?.status === "active" && current.capacity >= guests)
    return current;
  return (
    rooms
      .filter((room) => room.status === "active" && room.capacity >= guests)
      .sort(
        (a, b) =>
          Number(b.category === current?.category) -
            Number(a.category === current?.category) || a.capacity - b.capacity,
      )[0] || null
  );
}
