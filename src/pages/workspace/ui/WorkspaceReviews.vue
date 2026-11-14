<script setup>
import { useI18n } from "vue-i18n";
import { timeLabel } from "@/shared/lib";
const { t } = useI18n();
defineProps(["filteredReviews", "busy"]);
const emit = defineEmits(["moderate"]);
</script>
<template>
  <div>
    <article
      v-for="review in filteredReviews"
      :key="review.id"
      class="staff-review"
    >
      <strong
        >{{ review.rating }} / 5 ·
        {{
          review.status === "pending"
            ? t("staff.underReview")
            : review.status === "approved"
              ? t("staff.published")
              : t("staff.rejected")
        }}</strong
      >
      <small
        >{{ timeLabel(review.createdAt) }} {{ t("staff.verifiedStay") }}</small
      >
      <p>{{ review.text }}</p>
      <div class="staff-review-photos">
        <a
          v-for="photo in review.photos"
          :key="photo"
          :href="photo"
          target="_blank"
          rel="noopener noreferrer"
          ><img :src="photo" :alt="t('staff.guestPhoto')" loading="lazy"
        /></a>
      </div>
      <label class="editor-form"
        >{{ t("staff.resortReply")
        }}<textarea v-model="review.reply" maxlength="2000" rows="3"></textarea>
      </label>
      <div class="row-actions">
        <button
          class="primary"
          :disabled="busy"
          @click="emit('moderate', review, 'approved')"
        >
          {{ t("staff.publishReview") }}</button
        ><button
          class="secondary"
          :disabled="busy"
          @click="emit('moderate', review, 'rejected')"
        >
          {{ t("staff.hideReview") }}
        </button>
      </div>
    </article>
  </div>
</template>
