<script setup>
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
const { t } = useI18n();
const route = useRoute();
const links = [
  {
    to: "/staff/overview",
    key: "staff.overview",
    icon: "M3 3h7v7H3ZM14 3h7v7h-7ZM3 14h7v7H3ZM14 14h7v7h-7Z",
  },
  {
    to: "/staff/bookings",
    key: "staff.bookings",
    icon: "M4 5h16v16H4ZM8 2v6m8-6v6M4 11h16",
  },
  {
    to: "/staff/analytics",
    key: "staff.analytics",
    icon: "M4 3v18h18M8 16l5-6 4 3 5-8",
  },
  {
    to: "/staff/more",
    key: "common.mobile.manage",
    icon: "M4 6h16M4 12h16M4 18h16",
  },
];
</script>
<template>
  <nav
    v-if="route.path !== '/staff/login'"
    class="mobile-tabs staff-mobile-tabs"
    :aria-label="t('staff.staffWorkspace')"
  >
    <RouterLink v-for="item in links" :key="item.to" :to="item.to">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.7"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path :d="item.icon" />
      </svg>
      <span>{{ t(item.key) }}</span>
    </RouterLink>
  </nav>
</template>
