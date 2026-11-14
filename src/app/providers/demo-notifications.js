import { ApiError } from "../../shared/api/index.js";
const fail = (message, status) => {
  throw new ApiError(message, status);
};

export function requireNotificationScope(db, user, resortId = "") {
  if (!user) fail("Войдите в кабинет сотрудника.", 401);
  if (!["admin", "manager"].includes(user.role))
    fail("Уведомления о бронированиях недоступны для этой роли.", 403);
  const accessibleResortIds = new Set(
    user.role === "admin" ? db.resorts.map((r) => r.id) : user.resortIds || [],
  );
  if (resortId && !accessibleResortIds.has(resortId))
    fail("У вас нет доступа к этому санаторию.", 403);
  return accessibleResortIds;
}

export function demoNotifications({
  db,
  user,
  method,
  pathname,
  params,
  payload,
  persist,
}) {
  if (pathname === "/staff/notifications" && method === "GET") {
    const resortId = params.get("resortId");
    const accessibleResortIds = requireNotificationScope(db, user, resortId);
    const unreadOnly = ["1", "true", "yes"].includes(
      (params.get("unread") || "").toLowerCase(),
    );
    const scopedNotifications = (db.notifications || []).filter(
      (n) =>
        n.recipientId === user.id &&
        accessibleResortIds.has(n.resortId) &&
        (!resortId || n.resortId === resortId),
    );
    const unreadCount = scopedNotifications.filter((n) => !n.readAt).length;
    const items = (
      unreadOnly
        ? scopedNotifications.filter((n) => !n.readAt)
        : scopedNotifications
    ).slice(0, 100);
    return { handled: true, value: { items, unreadCount } };
  }
  if (pathname === "/staff/notifications/read-all" && method === "POST") {
    const resortId = payload?.resortId || params.get("resortId");
    const accessibleResortIds = requireNotificationScope(db, user, resortId);
    let updated = 0;
    const nowIso = new Date().toISOString();
    for (const n of db.notifications || []) {
      if (
        n.recipientId === user.id &&
        accessibleResortIds.has(n.resortId) &&
        (!resortId || n.resortId === resortId) &&
        !n.readAt
      ) {
        n.readAt = nowIso;
        updated++;
      }
    }
    persist();
    const unreadCount = (db.notifications || []).filter(
      (n) =>
        n.recipientId === user.id &&
        accessibleResortIds.has(n.resortId) &&
        !n.readAt,
    ).length;
    return { handled: true, value: { updated, unreadCount } };
  }
  const notifReadMatch = pathname.match(
    /^\/staff\/notifications\/([^/]+)\/read$/,
  );
  if (notifReadMatch && method === "POST") {
    const accessibleResortIds = requireNotificationScope(db, user);
    const notif = (db.notifications || []).find(
      (n) =>
        n.id === notifReadMatch[1] &&
        n.recipientId === user.id &&
        accessibleResortIds.has(n.resortId),
    );
    if (!notif) fail("Уведомление не найдено.", 404);
    if (!notif.readAt) {
      notif.readAt = new Date().toISOString();
      persist();
    }
    return { handled: true, value: notif };
  }
  return { handled: false };
}
