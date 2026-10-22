import { ownerOf, normalizePhone } from "./demo-guest-auth.js";
import { ApiError } from "../../shared/api/index.js";

const fail = (message, status = 422) => {
  throw new ApiError(message, status);
};
const publicProfile = ({
  id,
  name,
  phone,
  avatarUrl = "",
  version,
  createdAt,
  updatedAt,
}) => ({
  id,
  name,
  phone,
  avatarUrl,
  version,
  createdAt,
  updatedAt,
});
export function upgradeGuests(db) {
  db.guestProfiles ||= [];
  const owners = new Set([
    db.clientId,
    ownerOf(db),
    ...db.bookings.filter((b) => b.source === "website").map((b) => b.ownerId),
  ]);
  for (const owner of owners) {
    if (!owner || db.guestProfiles.some((p) => p.owner === owner)) continue;
    const first = db.bookings.find(
      (b) => b.ownerId === owner && b.source === "website",
    );
    const at = first?.createdAt || db.audit.at(-1)?.at || "";
    db.guestProfiles.push({
      id: `guest-${owner}`,
      owner,
      name: first?.guestLabel || "",
      phone: "",
      version: 1,
      createdAt: at,
      updatedAt: at,
    });
  }
  for (const b of db.bookings) {
    b.guestProfileId ||=
      b.source === "website"
        ? db.guestProfiles.find((p) => p.owner === b.ownerId)?.id
        : null;
    b.stayStatus ||= "not_arrived";
    b.checkedInAt ||= null;
    b.checkedOutAt ||= null;
  }
}
export function demoGuestRequest({
  db,
  user,
  method,
  pathname,
  payload,
  commit,
  authorize,
  version,
}) {
  const done = (value) => ({ handled: true, value });
  const bundle = (profile, scope = () => true) => ({
    profile: publicProfile(profile),
    bookings: db.bookings
      .filter((b) => b.guestProfileId === profile.id && scope(b))
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
  });
  if (pathname === "/profile") {
    const profile = db.guestProfiles.find((p) => p.owner === ownerOf(db));
    if (method === "GET") return done(bundle(profile));
    if (method === "PATCH") {
      if (
        db.guestAccount &&
        normalizePhone(payload.phone) !== db.guestAccount.phone
      )
        throw new ApiError(
          "Изменение подтверждённого номера требует отдельной проверки.",
          422,
          {},
          "phone_change_requires_verification",
        );
      if (
        Object.keys(payload).some((k) => !["name", "phone"].includes(k)) ||
        typeof payload.name !== "string" ||
        payload.name.trim().length < 1 ||
        payload.name.trim().length > 80 ||
        typeof payload.phone !== "string" ||
        !/^\+?[0-9 ()-]{7,30}$/.test(payload.phone)
      )
        fail(
          "Укажите имя до 80 символов и телефон. Используйте вымышленные данные в демо.",
        );
      const before = { ...profile };
      Object.assign(profile, {
        name: payload.name.trim(),
        phone: db.guestAccount?.phone || payload.phone.trim(),
        version: profile.version + 1,
        updatedAt: new Date().toISOString(),
      });
      commit("profiles", profile, before, "update");
      return done(bundle(profile));
    }
  }
  const guest = pathname.match(/^\/guests\/([^/]+)$/);
  if (guest && method === "GET") {
    if (!user) fail("Войдите в кабинет сотрудника.", 401);
    const profile = db.guestProfiles.find((p) => p.id === guest[1]);
    const scope = (b) => user.role === "admin" || b.resortId === user.resortId;
    if (
      !profile ||
      !db.bookings.some((b) => b.guestProfileId === profile.id && scope(b))
    )
      fail("Гость не найден.", 404);
    return done(bundle(profile, scope));
  }
  const stay = pathname.match(/^\/bookings\/([^/]+)\/(check-in|check-out)$/);
  if (stay && method === "POST") {
    const b = db.bookings.find((b) => b.id === stay[1]);
    if (!b) fail("Бронирование не найдено.", 404);
    authorize(b.resortId);
    version(b);
    if (b.status !== "confirmed" || b.payment?.status !== "paid")
      fail("Нужна подтверждённая и оплаченная бронь.", 409);
    const today = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Almaty",
    }).format(new Date());
    if (
      stay[2] === "check-in" &&
      (b.checkedInAt || today < b.start || today >= b.end)
    )
      fail("Заселение возможно в даты проживания и только один раз.", 409);
    if (stay[2] === "check-out" && (!b.checkedInAt || b.checkedOutAt))
      fail("Сначала отметьте заселение.", 409);
    const before = JSON.parse(JSON.stringify(b));
    if (stay[2] === "check-in") {
      b.checkedInAt = new Date().toISOString();
      b.stayStatus = "in_house";
    } else {
      b.checkedOutAt = new Date().toISOString();
      b.stayStatus = "checked_out";
    }
    b.version++;
    return done(commit("bookings", b, before, stay[2]));
  }
  return { handled: false };
}

export function freezeDemoReceipt(db, booking, payment) {
  const resort = db.resorts.find((r) => r.id === booking.resortId);
  return {
    source: "demo",
    number: `DEMO-${payment.id.slice(0, 8).toUpperCase()}`,
    issuedAt: payment.createdAt,
    paymentId: payment.id,
    bookingId: booking.id,
    resortName: booking.resortName,
    resortAddress: resort?.address || "",
    roomName: booking.roomName,
    unit: booking.unit,
    start: booking.start,
    end: booking.end,
    guests: booking.guests,
    guestLabel: booking.guestLabel,
    tariffName: booking.tariffName,
    regularNightly: booking.originalNightly ?? booking.nightly,
    nightly: booking.nightly,
    nights: booking.nights,
    discountPercent: booking.discountPercent || 0,
    total: payment.amount,
    currency: "KZT",
    checkinAt: booking.cancellationPolicy?.checkinAt || null,
    timeZone:
      booking.cancellationPolicy?.timeZone || resort?.timeZone || "Asia/Almaty",
    paymentMode: "demo",
    notice:
      "Демо-квитанция. Не чек Kaspi и не фискальный документ. Реальные деньги не списывались.",
  };
}
