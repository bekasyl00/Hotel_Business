<script setup>
import { onMounted, onBeforeUnmount, ref } from "vue";
import { useI18n } from "vue-i18n";
const { t } = useI18n();
const online = ref(navigator.onLine);
const update = () => {
  online.value = navigator.onLine;
};
onMounted(() => {
  window.addEventListener("online", update);
  window.addEventListener("offline", update);
});
onBeforeUnmount(() => {
  window.removeEventListener("online", update);
  window.removeEventListener("offline", update);
});
const links = [
  { to: "/", key: "public.catalogue", icon: "M3 10 12 3l9 7v11h-6v-7H9v7H3Z" },
  {
    to: "/bookings",
    key: "common.mobile.bookings",
    icon: "M4 5h16v16H4ZM8 2v6m8-6v6M4 11h16",
  },
  {
    to: "/profile",
    key: "common.mobile.profile",
    icon: "M20 21v-2a8 8 0 0 0-16 0v2M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8",
  },
];
</script>
<template>
  <p v-if="!online" class="mobile-offline" role="status">
    {{ t("common.mobile.offline") }}
  </p>
  <nav class="mobile-tabs" :aria-label="t('public.mainNavigation')">
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
