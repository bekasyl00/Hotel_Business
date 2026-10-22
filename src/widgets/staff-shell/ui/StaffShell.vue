<script setup>
import { computed } from "vue";
import { useSessionStore } from "@/entities/session";
const props = defineProps({ section: String });
const emit = defineEmits(["logout"]);
const session = useSessionStore();
const nav = computed(() => [
  ["overview", "◫", "Обзор"],
  ["resorts", "⌖", session.isAdmin ? "Санатории" : "Мой санаторий"],
  ["rooms", "▦", "Номера"],
  ["tariffs", "◈", "Тарифы"],
  ["bookings", "▤", "Бронирования"],
  ["history", "◷", "История изменений"],
  ...(session.isAdmin ? [["accounts", "♙", "Управляющие"]] : []),
]);
</script>
<template>
  <div class="staff-layout">
    <aside class="staff-sidebar">
      <RouterLink to="/" class="staff-brand"
        ><img src="/assets/logo.svg" alt="" width="32" /><span
          >тыныс.</span
        ></RouterLink
      ><span class="sidebar-caption">РАБОЧЕЕ ПРОСТРАНСТВО</span>
      <nav aria-label="Кабинет сотрудника">
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
            session.isAdmin ? "Администратор" : "Управляющий"
          }}</strong
          ><small>{{ session.user?.login }}</small>
        </div>
        <button
          class="logout-button"
          aria-label="Выйти из кабинета"
          @click="emit('logout')"
        >
          ↪
        </button>
      </div>
    </aside>
    <div class="staff-content">
      <header class="staff-topbar">
        <span
          >Кабинет /
          <strong>{{
            session.isAdmin ? "Платформа" : "Санаторий"
          }}</strong></span
        ><RouterLink to="/">Открыть сайт ↗</RouterLink>
      </header>
      <slot />
    </div>
  </div>
</template>
