<script setup>
import { useI18n } from "vue-i18n";
import { computed } from "vue";
import { useSessionStore } from "@/entities/session";
import { LanguageSwitcher } from "@/shared/ui";
import { publicUrl, isStaffApp, isDemo } from "@/shared/config";
const { t } = useI18n();
const props = defineProps({ section: String });
const emit = defineEmits(["logout"]);
const session = useSessionStore();
const nav = computed(() => [
  ["overview", "◫", t("staff.overview")],
  ["analytics", "↗", t("staff.analytics")],
  ["resorts", "⌖", session.isAdmin ? t("staff.resorts") : t("staff.myResort")],
  ["rooms", "▦", t("staff.rooms")],
  ["tariffs", "◈", t("staff.tariffs")],
  ["bookings", "▤", t("staff.bookings")],
  ["reviews", "☆", t("staff.reviews")],
  ["history", "◷", t("staff.history")],
  ...(session.isAdmin ? [["accounts", "♙", t("staff.managers")]] : []),
]);
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
          >{{ title }}</RouterLink
        >
      </nav>
      <div class="sidebar-footer">
        <span class="avatar">{{ session.user?.name[0] }}</span>
        <div>
          <strong>{{
            session.isAdmin ? t("staff.admin") : t("staff.manager")
          }}</strong
          ><small>{{ session.user?.login }}</small>
        </div>
        <button
          class="logout-button"
          :aria-label="t('staff.signOut')"
          @click="emit('logout')"
        >
          ↪
        </button>
      </div>
    </aside>
    <div class="staff-content">
      <header class="staff-topbar">
        <span
          >{{ t("staff.workspaceBreadcrumb") }}
          <strong>{{
            session.isAdmin ? t("staff.platform") : t("staff.resort")
          }}</strong></span
        >
        <div class="staff-topbar-actions">
          <LanguageSwitcher />
          <a v-if="!isStaffApp" :href="publicUrl">{{
            t("staff.openWebsite")
          }}</a>
          <template v-else
            ><span v-if="isDemo" class="demo-badge">DEMO</span
            ><button class="text-button" @click="emit('logout')">
              {{ t(isStaffApp ? "common.mobile.logout" : "staff.signOut") }}
            </button></template
          >
        </div>
      </header>
      <slot />
    </div>
  </div>
</template>
<style scoped>
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
  .staff-topbar {
    min-height: 52px;
  }
  .staff-topbar-actions {
    gap: 10px;
  }
}
</style>
