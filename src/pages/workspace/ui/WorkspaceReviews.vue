<script setup>
import { computed } from "vue";
import { useBookingStore } from "@/entities/booking";
import { GuestIdentity } from "@/shared/ui";
import { useI18n } from "vue-i18n";
import { timeLabel } from "@/shared/lib";
const { t } = useI18n();
const bookings = useBookingStore();
const props = defineProps(["filteredReviews", "busy"]);
const authors = computed(() => new Map(bookings.items.map(booking => [booking.id, booking])));
const entries = computed(() => props.filteredReviews.map(review => ({
  review, author: authors.value.get(review.bookingId),
})));
const emit = defineEmits(["moderate"]);
</script>
<template>
  <div>
    <article
      v-for="{ review, author } in entries"
      :key="review.id"
      class="staff-review"
    >
      <GuestIdentity v-if="author" class="review-author"
        :photo="author.guestAvatarUrl" :name="author.guestLabel">
        <RouterLink v-if="author.guestProfileId"
          :to="`/staff/guests/${author.guestProfileId}`">
          {{ author.guestLabel }}
        </RouterLink>
        <span v-else>{{ author.guestLabel }}</span>
      </GuestIdentity>
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
<style scoped>
.review-author { --avatar-size: 30px; margin-bottom: .5rem; }
</style>
