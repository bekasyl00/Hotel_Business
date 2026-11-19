<script setup>
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { request } from "@/shared/api";
import WorkspaceReviews from "./WorkspaceReviews.vue";

const props = defineProps({ id: String, busy: Boolean });
const emit = defineEmits(["loaded", "moderate"]);
const { t } = useI18n();
const review = ref(null), error = ref(""), attempt = ref(0);
watch([() => props.id, attempt], async ([id], _, onCleanup) => {
  let current = true;
  onCleanup(() => { current = false; });
  review.value = null;
  error.value = "";
  try {
    const item = await request("GET", `/reviews/${encodeURIComponent(id)}`);
    if (current) {
      review.value = item;
      emit("loaded", item);
    }
  } catch (e) {
    if (current) error.value = e.message;
  }
}, { immediate: true });
</script>
<template>
  <section class="surface review-detail">
    <RouterLink to="/staff/reviews">← {{ t("staff.notifications.allReviews") }}</RouterLink>
    <div v-if="error" role="alert">
      <p>{{ error }}</p>
      <button class="secondary" @click="attempt++">{{ t("staff.retryLoading") }}</button>
    </div>
    <WorkspaceReviews v-else-if="review" :filtered-reviews="[review]" :busy="busy"
      @moderate="(item, status) => emit('moderate', item, status)" />
    <p v-else role="status">{{ t("staff.loadingWorkspace") }}</p>
  </section>
</template>
<style scoped>
.review-detail > a { display: inline-block; margin-bottom: .75rem; }
</style>
