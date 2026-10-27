import { ApiError } from "../../shared/api/index.js";

const DAY = 86_400_000;
const OFFSET = 5 * 3_600_000;
const STATUS_NAMES = ["pending", "confirmed", "rejected", "cancelled"];
const fail = (message, status = 422) => {
  throw new ApiError(message, status);
};
const isoDay = (at) => new Date(at).toISOString().slice(0, 10);
const amount = (value) => (Number.isFinite(Number(value)) ? Number(value) : 0);
function parseDay(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || ""))
    fail("Выберите начало и конец периода.");
  const at = Date.parse(`${value}T00:00:00Z`);
  if (!Number.isFinite(at) || isoDay(at) !== value)
    fail("Укажите корректные даты периода.");
  const year = Number(value.slice(0, 4));
  if (year < 2 || year > 9998) fail("Дата выходит за допустимый диапазон.");
  return at;
}
function fresh() {
  return {
    bookingCount: 0,
    bookedAmount: 0,
    grossReceived: 0,
    refunds: 0,
    netReceived: 0,
    reviewCount: 0,
    averageRating: null,
    statuses: Object.fromEntries(STATUS_NAMES.map((s) => [s, 0])),
    ratingTotal: 0,
    ratingCount: 0,
  };
}
function finish(row, statuses = false) {
  const { ratingTotal, ratingCount, statuses: stateCounts, ...data } = row;
  data.netReceived = data.grossReceived - data.refunds;
  data.averageRating = ratingCount
    ? Math.floor((ratingTotal * 200 + ratingCount) / (ratingCount * 2)) / 100
    : null;
  if (statuses) data.statuses = stateCounts;
  return data;
}
function bucket(date, granularity) {
  if (granularity === "month") return `${date.slice(0, 7)}-01`;
  if (granularity === "week") {
    const at = parseDay(date);
    return isoDay(at - ((new Date(at).getUTCDay() + 6) % 7) * DAY);
  }
  return date;
}
function add(target, event) {
  if (event.kind === "booking") {
    target.bookingCount++;
    target.bookedAmount += event.amount;
    if (STATUS_NAMES.includes(event.status)) target.statuses[event.status]++;
  } else if (event.kind === "payment") target.grossReceived += event.amount;
  else if (event.kind === "refund") target.refunds += event.amount;
  else {
    target.reviewCount++;
    if (event.status === "approved") {
      target.ratingTotal += event.rating;
      target.ratingCount++;
    }
  }
}

export function demoAnalytics(db, user, params, now = Date.now()) {
  if (!user) fail("Войдите в кабинет сотрудника.", 401);
  if (user.role !== "admin" && !user.resortId)
    fail("У вас нет доступа к санаторию.", 403);
  const available = db.resorts.filter(
    (r) => user.role === "admin" || r.id === user.resortId,
  );
  const requestedResort = params.get("resortId");
  if (requestedResort && !available.some((r) => r.id === requestedResort))
    fail("Санаторий недоступен.", user.role === "admin" ? 404 : 403);
  const resorts = available.filter(
    (r) => !requestedResort || r.id === requestedResort,
  );
  const resortIds = new Set(resorts.map((r) => r.id));
  const end = params.get("end") ?? isoDay(now + OFFSET);
  const endDay = parseDay(end);
  const start = params.get("start") ?? isoDay(endDay - 27 * DAY);
  const startDay = parseDay(start);
  const days = (endDay - startDay) / DAY + 1;
  if (days < 1 || days > 366) fail("Период должен быть от 1 до 366 дней.");
  const granularity = params.get("granularity") || "day";
  if (!["day", "week", "month"].includes(granularity))
    fail("Выберите группировку по дням, неделям или месяцам.");
  const period = { start, end, granularity, timeZone: "Asia/Almaty" };
  const previousPeriod = {
    start: isoDay(startDay - days * DAY),
    end: isoDay(startDay - DAY),
  };
  const rooms = db.rooms.filter((r) => resortIds.has(r.resortId));
  const bookings = db.bookings.filter((b) => resortIds.has(b.resortId));
  const bookingById = new Map(bookings.map((b) => [b.id, b]));
  const events = [];
  const push = (createdAt, value) => {
    const at = Date.parse(createdAt || "");
    if (Number.isFinite(at))
      events.push({ date: isoDay(at + OFFSET), ...value });
  };
  for (const b of bookings)
    push(b.createdAt, {
      kind: "booking",
      resortId: b.resortId,
      roomId: b.roomId,
      amount: amount(b.total),
      status: b.status,
    });
  for (const p of db.payments || []) {
    const b = bookingById.get(p.bookingId);
    if (!b || p.outcome !== "success") continue;
    push(p.createdAt, {
      kind: "payment",
      resortId: b.resortId,
      roomId: b.roomId,
      amount: amount(p.amount),
    });
  }
  let refundDataIncomplete = false;
  for (const b of bookings) {
    if (!b.cancellation) continue;
    const refundAmount = amount(b.cancellation.refundAmount);
    if (!refundAmount) continue;
    if (!Number.isFinite(Date.parse(b.cancellation.createdAt || ""))) {
      refundDataIncomplete = true;
      continue;
    }
    push(b.cancellation.createdAt, {
      kind: "refund",
      resortId: b.resortId,
      roomId: b.roomId,
      amount: refundAmount,
    });
  }
  for (const r of db.reviews || []) {
    const b = bookingById.get(r.bookingId);
    if (!b || r.resortId !== b.resortId) continue;
    push(r.createdAt, {
      kind: "review",
      resortId: b.resortId,
      roomId: b.roomId,
      status: r.status,
      rating: amount(r.rating),
    });
  }
  const totals = fresh(),
    previousTotals = fresh();
  const series = new Map();
  for (let at = startDay; at <= endDay; at += DAY) {
    const key = bucket(isoDay(at), granularity);
    if (!series.has(key)) series.set(key, fresh());
  }
  const resortRows = new Map(resorts.map((r) => [r.id, fresh()]));
  const roomRows = new Map(rooms.map((r) => [r.id, fresh()]));
  for (const event of events) {
    if (event.date >= previousPeriod.start && event.date <= previousPeriod.end)
      add(previousTotals, event);
    if (event.date < start || event.date > end) continue;
    add(totals, event);
    add(series.get(bucket(event.date, granularity)), event);
    if (resortRows.has(event.resortId))
      add(resortRows.get(event.resortId), event);
    if (roomRows.has(event.roomId)) add(roomRows.get(event.roomId), event);
  }
  const rank = (key) => (a, b) =>
    b.netReceived - a.netReceived ||
    (a[key] < b[key] ? -1 : a[key] > b[key] ? 1 : 0);
  const byResort = resorts
    .map((r) => ({
      resortId: r.id,
      name: r.name,
      ...finish(resortRows.get(r.id), true),
    }))
    .sort(rank("resortId"));
  const byRoom = rooms
    .map((r) => ({
      roomId: r.id,
      resortId: r.resortId,
      name: r.title,
      number: r.number,
      ...finish(roomRows.get(r.id), true),
    }))
    .sort(rank("roomId"));
  return {
    period,
    previousPeriod,
    paymentMode: "demo",
    totals: finish(totals, true),
    previousTotals: finish(previousTotals, true),
    series: [...series].map(([date, data]) => ({ date, ...finish(data) })),
    byResort: byResort.slice(0, 500),
    byRoom: byRoom.slice(0, 500),
    resorts: available
      .map(({ id, name }) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id)),
    truncated: { byResort: byResort.length > 500, byRoom: byRoom.length > 500 },
    refundDataIncomplete,
  };
}
