import { ref } from "vue";
import { request } from "@/shared/api";

export function useWorkspaceNotifications({ session, selected, error, busy }) {
  const notifications = ref([]);
  const unreadNotifications = ref(0);
  let generation = 0;
  const pendingReads = new Set();
  async function loadNotifications() {
    if (!session.user || session.isAccountant) return;
    const run = ++generation;
    try {
      const res = await request("GET", "/staff/notifications");
      if (run !== generation) return;
      notifications.value = res.items || [];
      unreadNotifications.value = Number(res.unreadCount || 0);
    } catch (e) {
      if (run === generation) error.value = e.message;
    }
  }
  async function markNotificationRead(item) {
    if (
      item.readAt ||
      notifications.value.find((notification) => notification.id === item.id)
        ?.readAt ||
      pendingReads.has(item.id)
    )
      return;
    pendingReads.add(item.id);
    generation++;
    try {
      const updated = await request(
        "POST",
        `/staff/notifications/${item.id}/read`,
        {},
      );
      const idx = notifications.value.findIndex((n) => n.id === item.id);
      if (idx >= 0) notifications.value[idx] = updated;
      unreadNotifications.value =
        updated.unreadCount != null
          ? Number(updated.unreadCount)
          : Math.max(0, unreadNotifications.value - 1);
    } catch (e) {
      error.value = e.message;
    } finally {
      pendingReads.delete(item.id);
    }
  }
  async function markAllNotificationsRead() {
    generation++;
    busy.value = true;
    error.value = "";
    try {
      const res = await request("POST", "/staff/notifications/read-all", {
        resortId: selected.value || undefined,
      });
      unreadNotifications.value = Number(res.unreadCount || 0);
      await loadNotifications();
    } catch (e) {
      error.value = e.message;
    } finally {
      busy.value = false;
    }
  }
  return {
    notifications,
    unreadNotifications,
    loadNotifications,
    markNotificationRead,
    markAllNotificationsRead,
  };
}
