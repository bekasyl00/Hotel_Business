import { ownerOf } from "./demo-guest-auth.js";
import { ApiError } from "../../shared/api/index.js";
import { freezeDemoReceipt } from "./demo-guests.js";

export const categories = [
  { id: "wellness", name: "Оздоровление" },
  { id: "family", name: "Семейный отдых" },
  { id: "premium", name: "Премиум" },
  { id: "nature", name: "На природе" },
];
const fail = (message, status = 422) => {
  throw new ApiError(message, status);
};
export function safeMedia(items = []) {
  if (!Array.isArray(items) || items.length > 12)
    fail("Можно добавить до 12 медиафайлов.");
  return items.map((item) => {
    if (
      !item ||
      !["image", "video"].includes(item.kind) ||
      !safeUrl(item.url) ||
      typeof item.alt !== "string" ||
      item.alt.length > 200
    )
      fail("Проверьте тип, ссылку и описание медиа.");
    return { kind: item.kind, url: item.url, alt: item.alt };
  });
}
export function safeUrl(value) {
  if (
    typeof value !== "string" ||
    value.length > 1500 ||
    /[\x00-\x20\\]/.test(value)
  )
    return false;
  try {
    if (decodeURIComponent(value).split("/").includes("..")) return false;
    if (/^\/(assets|media)\/[A-Za-z0-9_./-]+$/.test(value)) return true;
    const url = new URL(value);
    return (
      url.protocol === "https:" &&
      Boolean(url.hostname) &&
      !url.username &&
      !url.password
    );
  } catch {
    return false;
  }
}
export function amenities(value = []) {
  const result =
    typeof value === "string"
      ? value
          .split("\n")
          .map((v) => v.trim())
          .filter(Boolean)
      : value;
  if (
    !Array.isArray(result) ||
    result.length > 30 ||
    result.some((v) => typeof v !== "string" || v.length > 200)
  )
    fail("Укажите до 30 удобств.");
  return result;
}
export function upgradeMarketplace(db) {
  db.reviews ||= [];
  db.payments ||= [];
  db.resorts.forEach((r, i) => {
    const approved = db.reviews.filter(
      (review) => review.resortId === r.id && review.status === "approved",
    );
    r.reviewCount = approved.length;
    r.reviewRating = approved.length
      ? Math.round(
          (approved.reduce((sum, review) => sum + review.rating, 0) /
            approved.length) *
            10,
        ) / 10
      : null;
    r.category ||= categories[i % categories.length].id;
    r.resortClass ||= ["comfort", "standard", "premium"][i % 3];
    r.checkInTime ||= "14:00";
    r.timeZone ||= "Asia/Almaty";
    r.media ||= [
      {
        kind: "image",
        url: "/assets/resort.jpg",
        alt: "Иллюстративное фото курорта",
      },
    ];
    r.amenities ||= ["Wi-Fi", "Парковка"];
  });
  db.rooms.forEach((r) => {
    r.description ||=
      "Светлый номер для спокойного отдыха. Фотография иллюстративная; условия уточняйте у управляющего.";
    r.media ||= [
      {
        kind: "image",
        url: "/assets/room.jpg",
        alt: "Иллюстративное фото номера",
      },
    ];
    r.amenities ||= ["Санузел", "Кондиционер", "Wi-Fi"];
  });
  db.tariffs.forEach((t) => {
    t.priceKind ||= "regular";
    t.discountPercent ||= 0;
  });
  db.payments
    .filter((payment) => payment.outcome === "success")
    .forEach((payment) => {
      payment.receiptUrl ||= `/receipts/${payment.id}`;
      const booking = db.bookings.find((b) => b.id === payment.bookingId);
      if (booking?.payment?.id === payment.id)
        booking.payment.receiptUrl = payment.receiptUrl;
    });
}
export function freezePolicy(resort, start) {
  return {
    checkinAt: `${start}T${resort.checkInTime?.slice(0, 5) || "14:00"}:00+05:00`,
    checkInTime: resort.checkInTime || "14:00",
    timeZone: "Asia/Almaty",
    partialRefundPercent: 70,
    mode: "demo",
  };
}
export function refundPreview(booking, staff = false, now = Date.now()) {
  if (booking.cancellation) return { ...booking.cancellation, finalized: true };
  const policy = booking.cancellationPolicy || freezePolicy({}, booking.start);
  const hoursBeforeCheckin = (Date.parse(policy.checkinAt) - now) / 3600000;
  const refundPercent =
    hoursBeforeCheckin >= 48 ? 100 : hoursBeforeCheckin >= 24 ? 70 : 0;
  const paidAmount =
    booking.payment?.status === "paid" ? booking.payment.amount : 0;
  return {
    ...policy,
    paidAmount,
    refundAmount: Math.floor((paidAmount * refundPercent) / 100),
    refundPercent,
    hoursBeforeCheckin,
    checkinAt: policy.checkinAt,
    policyText:
      "100% за 48 часов и более · 70% за 24–48 часов · менее 24 часов без возврата.",
    actorKind: staff ? "provider" : "guest",
  };
}
export function applyDemoCancellation(booking, staff = false) {
  const preview = refundPreview(booking, staff);
  if (preview.paidAmount) {
    booking.payment.refundedAmount = preview.refundAmount;
    if (preview.refundPercent === 100) booking.payment.status = "refunded";
    else if (preview.refundPercent)
      booking.payment.status = "partially_refunded";
  }
  return preview;
}
export function marketplaceRequest({
  db,
  user,
  method,
  pathname,
  params,
  payload,
  commit,
  authorize,
  version,
}) {
  const done = (value) => ({ handled: true, value });
  const publicResort = (id) =>
    db.resorts.find((r) => r.id === id && r.status === "published");
  const publicReview = ({
    id,
    resortId,
    rating,
    text,
    photos,
    reply,
    createdAt,
    verifiedStay,
  }) => ({
    id,
    resortId,
    rating,
    text,
    photos,
    reply,
    createdAt,
    verifiedStay,
  });
  const ownBooking = (id) => {
    const b = db.bookings.find(
      (b) => b.id === id && b.ownerId === ownerOf(db) && b.source === "website",
    );
    if (!b) fail("Бронирование не найдено.", 404);
    return b;
  };
  const receiptPath = pathname.match(/^\/receipts\/([^/]+)$/);
  if (receiptPath && method === "GET") {
    const payment = db.payments.find(
      (p) => p.id === receiptPath[1] && p.outcome === "success",
    );
    if (!payment) fail("Квитанция не найдена.", 404);
    const booking = db.bookings.find((b) => b.id === payment.bookingId);
    if (
      !booking ||
      (!(booking.ownerId === ownerOf(db) && booking.source === "website") &&
        (!user ||
          (user.role !== "admin" && user.resortId !== booking.resortId)))
    )
      fail("Квитанция не найдена.", 404);
    if (!payment.receipt) {
      const before = JSON.parse(JSON.stringify(payment));
      const receipt = freezeDemoReceipt(db, booking, payment);
      receipt.legacySnapshot = true;
      receipt.notice +=
        " Восстановлена при первом открытии: адрес санатория взят из текущего каталога.";
      payment.receipt = receipt;
      payment.receiptUrl = `/receipts/${payment.id}`;
      if (booking.payment?.id === payment.id) {
        booking.payment.receipt = receipt;
        booking.payment.receiptUrl = payment.receiptUrl;
      }
      commit("payments", payment, before, "restore_receipt");
    }
    return done({
      receipt: payment.receipt,
      payment: { ...payment, receiptUrl: `/receipts/${payment.id}` },
      refund: booking.cancellation?.paidAmount
        ? {
            amount: booking.cancellation.refundAmount,
            percent: booking.cancellation.refundPercent,
            createdAt: booking.cancellation.createdAt,
          }
        : null,
    });
  }
  if (method === "GET" && pathname === "/categories") return done(categories);
  const detail = pathname.match(/^\/(resorts|rooms)\/([^/]+)$/);
  if (method === "GET" && detail) {
    const room =
      detail[1] === "rooms"
        ? db.rooms.find((r) => r.id === detail[2] && r.status === "active")
        : null;
    const resort = publicResort(room?.resortId || detail[2]);
    if (!resort || (detail[1] === "rooms" && !room))
      fail("Страница не найдена.", 404);
    const tariffs = db.tariffs.filter(
      (t) => t.resortId === resort.id && t.status === "active",
    );
    return done(
      room
        ? { resort, room, tariffs }
        : {
            resort,
            rooms: db.rooms.filter(
              (r) => r.resortId === resort.id && r.status === "active",
            ),
            tariffs,
            reviews: db.reviews
              .filter(
                (r) => r.resortId === resort.id && r.status === "approved",
              )
              .map(publicReview),
          },
    );
  }
  if (pathname.startsWith("/cancellation-preview/") && method === "GET") {
    const id = pathname.split("/").at(-1);
    const b = db.bookings.find((b) => b.id === id);
    if (!b) fail("Бронирование не найдено.", 404);
    const staff = params.get("asStaff") === "true";
    if (staff) authorize(b.resortId);
    else ownBooking(id);
    return done(refundPreview(b, staff));
  }
  if (pathname === "/payments/demo" && method === "POST") {
    const b = ownBooking(payload.bookingId);
    if (
      !/^[0-9a-f-]{36}$/i.test(payload.requestId || "") ||
      !["success", "failed"].includes(payload.outcome)
    )
      fail("Некорректный запрос оплаты.");
    const previous = db.payments.find((p) => p.requestId === payload.requestId);
    if (previous) {
      if (previous.bookingId !== b.id || previous.outcome !== payload.outcome)
        fail("Ключ оплаты уже использован.", 409);
      return done(previous);
    }
    if (b.status !== "confirmed")
      fail("Дождитесь подтверждения управляющего.", 409);
    if (
      Date.now() >=
      Date.parse((b.cancellationPolicy || freezePolicy({}, b.start)).checkinAt)
    )
      fail("Время заезда уже наступило. Обратитесь к управляющему.", 409);
    if (["paid", "refunded", "partially_refunded"].includes(b.payment?.status))
      fail("Это бронирование уже оплачено.", 409);
    const payment = {
      id: crypto.randomUUID(),
      bookingId: b.id,
      resortId: b.resortId,
      requestId: payload.requestId,
      outcome: payload.outcome,
      status: payload.outcome === "success" ? "paid" : "failed",
      amount: b.total,
      refundedAmount: 0,
      paymentMode: "demo",
      provider: "kaspi-demo",
      currency: "KZT",
      createdAt: new Date().toISOString(),
    };
    const before = JSON.parse(JSON.stringify(b));
    if (payload.outcome === "success") {
      payment.receiptUrl = `/receipts/${payment.id}`;
      payment.receipt = freezeDemoReceipt(db, b, payment);
    }
    b.payment = payment;
    db.payments.push(payment);
    commit("bookings", b, before, "demo_payment");
    return done(payment);
  }
  if (pathname === "/reviews" && method === "GET") {
    if (!publicResort(params.get("resortId")))
      fail("Санаторий не найден.", 404);
    return done(
      db.reviews
        .filter(
          (r) =>
            r.resortId === params.get("resortId") && r.status === "approved",
        )
        .map(publicReview),
    );
  }
  if (pathname === "/reviews" && method === "POST") {
    if (user) fail("Сотрудники не могут оставлять отзывы о проживании.", 403);
    const b = ownBooking(payload.bookingId);
    if (
      b.status !== "confirmed" ||
      Date.parse(`${b.end}T00:00:00+05:00`) > Date.now()
    )
      fail("Оставить отзыв можно после подтверждённого проживания.", 403);
    if (db.reviews.some((r) => r.bookingId === b.id))
      fail("Отзыв об этом проживании уже есть.", 409);
    if (
      !Number.isInteger(payload.rating) ||
      payload.rating < 1 ||
      payload.rating > 5 ||
      typeof payload.text !== "string" ||
      payload.text.trim().length < 10 ||
      payload.text.length > 3000
    )
      fail("Укажите оценку и текст от 10 до 3000 символов.");
    if (
      !Array.isArray(payload.photos) ||
      payload.photos.length > 6 ||
      payload.photos.some((p) => !safeUrl(p))
    )
      fail("Добавьте до 6 фотографий.");
    const review = {
      id: crypto.randomUUID(),
      resortId: b.resortId,
      bookingId: b.id,
      rating: payload.rating,
      text: payload.text.trim(),
      photos: payload.photos,
      reply: "",
      status: "pending",
      version: 1,
      verifiedStay: true,
      createdAt: new Date().toISOString(),
    };
    db.reviews.push(review);
    b.reviewId = review.id;
    b.reviewStatus = review.status;
    return done(commit("reviews", review));
  }
  if (pathname.startsWith("/reviews/") && method === "PATCH") {
    const r = db.reviews.find((r) => r.id === pathname.split("/").at(-1));
    if (!r) fail("Отзыв не найден.", 404);
    authorize(r.resortId);
    version(r);
    if (
      !["approved", "rejected"].includes(payload.status) ||
      typeof (payload.reply ?? "") !== "string" ||
      (payload.reply || "").length > 2000
    )
      fail("Проверьте статус и ответ.");
    const before = JSON.parse(JSON.stringify(r));
    Object.assign(r, {
      status: payload.status,
      reply: payload.reply || "",
      version: r.version + 1,
    });
    const booking = db.bookings.find((b) => b.id === r.bookingId);
    if (booking) booking.reviewStatus = r.status;
    const reviews = db.reviews.filter(
      (review) =>
        review.resortId === r.resortId && review.status === "approved",
    );
    db.resorts.find((resort) => resort.id === r.resortId).rating =
      reviews.length
        ? Math.round(
            (reviews.reduce((sum, review) => sum + review.rating, 0) /
              reviews.length) *
              10,
          ) / 10
        : 0;
    return done(commit("reviews", r, before, "update"));
  }
  return { handled: false };
}
