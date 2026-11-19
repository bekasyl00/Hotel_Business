<script setup>
import { useI18n } from "vue-i18n";
import { timeLabel } from "@/shared/lib";
const { t } = useI18n();
defineProps(["filteredNotifications"]);
const emit = defineEmits(["read", "open-booking", "open-review"]);
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
          ><template v-if="item.kind !== 'review_created'">{{ item.title }} · </template>
          {{ t(`staff.notifications.${item.kind}`) }}</strong
        >
        <small>{{ timeLabel(item.createdAt) }}</small>
      </div>
      <p>{{ item.body }}</p>
      <div class="row-actions">
        <button
          v-if="item.reviewId" type="button" class="primary" @click="emit('open-review', item)"
        >{{ t("staff.notifications.openReview") }}</button>
        <button
          v-else-if="item.bookingId"
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
