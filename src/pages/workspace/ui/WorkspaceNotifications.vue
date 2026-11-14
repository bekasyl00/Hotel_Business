<script setup>
import { useI18n } from "vue-i18n";
import { timeLabel } from "@/shared/lib";
const { t } = useI18n();
defineProps(["filteredNotifications"]);
const emit = defineEmits(["read", "open-booking"]);
</script>
<template>
  <div class="audit-list">
    <article
      v-for="item in filteredNotifications"
      :key="item.id"
      class="staff-review"
      :style="{
        borderLeft: item.readAt ? '3px solid #cbd6cf' : '4px solid #143e2c',
      }"
    >
      <div class="row-actions" style="justify-content: space-between">
        <strong
          >{{ item.title }} ·
          {{ t(`staff.notifications.${item.kind}`) }}</strong
        >
        <small>{{ timeLabel(item.createdAt) }}</small>
      </div>
      <p>{{ item.body }}</p>
      <div class="row-actions">
        <button
          v-if="item.bookingId"
          type="button"
          class="primary"
          @click="emit('open-booking', item)"
        >
          {{ t("staff.notifications.openBooking") }}
        </button>
        <button
          v-if="!item.readAt"
          type="button"
          class="secondary"
          @click="emit('read', item)"
        >
          {{ t("staff.notifications.markRead") }}
        </button>
      </div>
    </article>
  </div>
</template>
