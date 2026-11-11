<script setup>
import { useI18n } from "vue-i18n";
import { staffNavigation } from "../model/navigation.js";
import { computed, ref, onMounted, onBeforeUnmount, watch } from "vue";
import { useSessionStore } from "@/entities/session";
import { LanguageSwitcher } from "@/shared/ui";
import { ArrivalCheckIn } from "@/features/arrival-check-in";
import { publicUrl, isStaffApp, isDemo } from "@/shared/config";
import { request } from "@/shared/api";
const { t } = useI18n();
const props = defineProps({
  section: String,
  unreadCount: { type: Number, default: null },
});
const emit = defineEmits(["logout", "unread"]);
const session = useSessionStore();
const localUnread = ref(0);
const badgeCount = computed(() =>
  props.unreadCount != null ? props.unreadCount : localUnread.value,
);
const canReceiveNotifications = computed(
  () => session.user && ["admin", "manager"].includes(session.user.role),
);
const nav = computed(() =>
  staffNavigation(session.user?.role).map(([key, icon, label]) => [
    key,
    icon,
    t(label),
  ]),
);
let pollTimer = null;
async function pollNotifications() {
  if (!canReceiveNotifications.value) return;
  if (typeof document !== "undefined" && document.visibilityState === "hidden")
    return;
  try {
    const res = await request("GET", "/staff/notifications?unread=1");
    localUnread.value = Number(res?.unreadCount || 0);
    emit("unread", localUnread.value);
  } catch {
    // ignore transient poll failures
  }
}
function onVisibilityChange() {
  if (typeof document !== "undefined" && document.visibilityState === "visible")
    pollNotifications();
}
watch(
  () => props.unreadCount,
  (val) => {
    if (val != null) localUnread.value = val;
  },
);
onMounted(() => {
  pollNotifications();
  pollTimer = setInterval(pollNotifications, 30000);
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", onVisibilityChange);
  }
  if (typeof window !== "undefined") {
    window.addEventListener("focus", pollNotifications);
  }
});
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
  if (typeof document !== "undefined") {
    document.removeEventListener("visibilitychange", onVisibilityChange);
  }
  if (typeof window !== "undefined") {
    window.removeEventListener("focus", pollNotifications);
  }
});
</script>
<template>
  <div class="staff-layout">
    <aside v-if="!isStaffApp" class="staff-sidebar">
      <a :href="publicUrl" class="staff-brand"
        ><img src="/assets/logo.svg" alt="" width="32" /><span>тыныс.</span></a
      ><span class="sidebar-caption">{{ t("staff.workspaceEyebrow") }}</span>
      <nav :aria-label="t('staff.staffWorkspace')">
        <RouterLink
          v-for="[key, icon, title] in nav"
          :key="key"
          :to="'/staff/' + key"
          :class="{ selected: section === key }"
          :aria-current="section === key ? 'page' : undefined"
          ><span aria-hidden="true">{{ icon }}</span
          >{{ title
          }}<span
            v-if="key === 'notifications' && badgeCount > 0"
            class="notif-badge"
            >{{ badgeCount }}</span
          ></RouterLink
        >
      </nav>
      <div class="sidebar-footer">
        <RouterLink
          class="sidebar-profile"
          to="/staff/profile"
          :aria-current="section === 'profile' ? 'page' : undefined"
        >
          <span class="avatar" aria-hidden="true">{{
            session.user?.name?.[0] || "•"
          }}</span>
          <div class="sidebar-profile-copy">
            <strong>{{
              session.user?.name ||
              t(
                session.isAdmin
                  ? "staff.admin"
                  : session.isAccountant
                    ? "common.accounting.role"
                    : "staff.manager",
              )
            }}</strong>
            <small>{{ session.user?.login }}</small>
            <span class="sidebar-profile-action"
              >{{ t("common.staffProfile.title") }} →</span
            >
          </div>
        </RouterLink>
        <button
          class="logout-button"
          :aria-label="t('staff.signOut')"
          @click="emit('logout')"
        >
          {{ t("common.mobile.logout") }}
        </button>
      </div>
    </aside>
    <div class="staff-content">
      <header class="staff-topbar">
        <span
          >{{ t("staff.workspaceBreadcrumb") }}
          <strong>{{
            session.isAdmin || session.isAccountant
              ? t("staff.platform")
              : t("staff.resort")
          }}</strong></span
        >
        <div class="staff-topbar-actions">
          <ArrivalCheckIn v-if="!isDemo && !session.isAccountant" />
          <RouterLink
            v-if="canReceiveNotifications"
            to="/staff/notifications"
            class="topbar-notif-link"
            :aria-current="section === 'notifications' ? 'page' : undefined"
            >{{ t("staff.notifications.title")
            }}<span v-if="badgeCount > 0" class="notif-badge">{{
              badgeCount
            }}</span></RouterLink
          >
          <RouterLink
            to="/staff/profile"
            :aria-current="section === 'profile' ? 'page' : undefined"
            >{{ t("common.staffProfile.title") }}</RouterLink
          >
          <LanguageSwitcher />
          <a v-if="!isStaffApp" :href="publicUrl">{{
            t("staff.openWebsite")
          }}</a>
          <span v-if="isStaffApp && isDemo" class="demo-badge">DEMO</span>
          <button class="text-button" @click="emit('logout')">
            {{ t(isStaffApp ? "common.mobile.logout" : "staff.signOut") }}
          </button>
        </div>
      </header>
      <slot />
    </div>
  </div>
</template>
<style scoped>
.notif-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  margin-left: 6px;
  border-radius: 999px;
  background: #143e2c;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
}
.topbar-notif-link {
  display: inline-flex;
  align-items: center;
}
.staff-sidebar {
  overflow-y: auto;
}
.sidebar-footer {
  margin-top: 24px;
  padding: 12px 0 0;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
}
.sidebar-profile {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border-radius: 10px;
  color: inherit;
  text-decoration: none;
  transition: background 0.15s ease;
}
.sidebar-profile .avatar {
  flex: 0 0 36px;
  height: 36px;
  background: #53694a1a;
}
.sidebar-profile-copy {
  min-width: 0;
}
.sidebar-profile strong {
  font-size: 12px;
  overflow-wrap: anywhere;
}
.sidebar-profile small {
  max-width: none;
  font-size: 11px;
}
.sidebar-profile-action {
  display: block;
  margin-top: 5px;
  font-size: 11px;
  font-weight: 600;
}
.sidebar-profile:hover,
.sidebar-profile[aria-current="page"],
.sidebar-footer .logout-button:hover {
  background: #53694a18;
}
.sidebar-profile:focus-visible,
.sidebar-footer .logout-button:focus-visible {
  outline: 2px solid #53694a;
  outline-offset: 2px;
}
.sidebar-footer .logout-button {
  width: 100%;
  min-height: 44px;
  border: 1px solid #53694a40;
  border-radius: 9px;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
  color: inherit;
  text-align: center;
}

.staff-topbar {
  height: auto;
  min-height: 76px;
  gap: 12px;
  flex-wrap: wrap;
  padding-block: 12px;
}
.staff-topbar-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}
@media (max-width: 760px) {
  .staff-layout .staff-sidebar {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 12px;
  }
  .staff-sidebar .staff-brand {
    grid-column: 1;
    grid-row: 1;
  }
  .staff-sidebar .sidebar-footer {
    position: static;
    inset: auto;
    grid-column: 2;
    grid-row: 1;
    justify-self: end;
    display: block;
    min-width: 0;
    max-width: 100%;
    margin: 0;
    padding: 0;
    border: 0;
  }
  .staff-sidebar .sidebar-profile {
    min-height: 44px;
    padding: 6px 8px;
    gap: 8px;
  }
  .sidebar-profile .avatar {
    display: grid;
    flex-basis: 32px;
    width: 32px;
    height: 32px;
  }
  .sidebar-profile strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 11px;
  }
  .sidebar-profile-action {
    margin-top: 2px;
    font-size: 10px;
  }
  .staff-sidebar .sidebar-footer .logout-button,
  .sidebar-profile small {
    display: none;
  }
  .staff-sidebar nav {
    grid-column: 1 / -1;
    grid-row: 2;
    min-width: 0;
    width: 100%;
    margin-top: 0;
    padding-top: 0;
  }
  .staff-topbar {
    min-height: 52px;
  }
  .staff-topbar-actions {
    gap: 10px;
  }
}
</style>
