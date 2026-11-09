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

export function monthsAt(birth, checkin) {
  const b = parts(birth),
    c = parts(checkin);
  if (!b || !c || birth > checkin) return null;
  return (c[0] - b[0]) * 12 + c[1] - b[1] - (c[2] < b[2] ? 1 : 0);
}

// This is only a date suggestion from the first six digits, not identity validation.
export function childDatePreview(value, checkin, today) {
  const input = String(value || "");
  if (!input) return { status: "empty" };
  if (!/^\d{1,12}$/.test(input)) return { status: "invalidIin" };
  if (input.length < 6) return { status: "incomplete" };
  const arrival = parts(checkin);
  if (!arrival || !parts(today)) return { status: "arrivalRequired" };
  const yy = Number(input.slice(0, 2));
  let year = Math.floor(arrival[0] / 100) * 100 + yy;
  if (year > arrival[0]) year -= 100;
  const birth = `${year}-${input.slice(2, 4)}-${input.slice(4, 6)}`;
  if (!parts(birth)) return { status: "invalidBirthDate" };
  if (birth > today || birth > checkin) return { status: "futureBirthDate" };
  const age = ageAt(birth, checkin);
  if (age >= 14) return { status: "overChildAge" };
  return {
    status: input.length === 12 ? "ready" : "incomplete",
    birth,
    age,
    months: monthsAt(birth, checkin),
  };
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
  const preview = childDatePreview(value, checkin, today);
  return preview.status === "ready" ? preview.birth : "";
}

export function partySize(adults, children, maxGuests = 4) {
  if (adults === "" || !Number.isInteger(Number(adults))) return null;
  if (!Number.isInteger(children) || children < 0) return null;
  const olderGuests = Number(adults),
    total = olderGuests + children;
  return olderGuests >= 1 && total <= maxGuests ? total : null;
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
