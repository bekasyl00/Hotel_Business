<script setup>
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { request } from "@/shared/api";
import { isDemo } from "@/shared/config";
import { DocumentFiles } from "@/shared/ui";
const props = defineProps({ bookingId: { type: String, required: true } });
const { t } = useI18n();
const documents = ref([]),
  error = ref(""),
  loading = ref(false);
watch(
  () => props.bookingId,
  async (id, old, onCleanup) => {
    let active = true;
    onCleanup(() => (active = false));
    documents.value = [];
    error.value = "";
    loading.value = true;
    try {
      if (!isDemo) {
        const result = await request("GET", `/bookings/${id}/documents`);
        if (active) documents.value = result;
      }
    } catch (e) {
      if (active) error.value = e.message;
    } finally {
      if (active) loading.value = false;
    }
  },
  { immediate: true },
);
</script>
<template>
  <section class="booking-documents">
    <h3>{{ t("common.accounting.documents") }}</h3>
    <p>{{ t("common.accounting.staffDocumentsHint") }}</p>
    <p v-if="loading" role="status">{{ t("common.accounting.fileLoading") }}</p>
    <p v-else-if="error" role="alert" class="form-error">{{ error }}</p>
    <p v-else-if="!documents.length">
      {{ t("common.accounting.staffDocumentsEmpty") }}
    </p>
    <article v-for="doc in documents" :key="doc.id">
      <h4>{{ t(`common.accounting.kinds.${doc.kind}`) }} · {{ doc.number }}</h4>
      <p>{{ t(`common.accounting.states.${doc.state}`) }}</p>
      <DocumentFiles
        :path="`/bookings/${bookingId}/documents/${doc.id}`"
        :number="doc.number"
      />
    </article>
  </section>
</template>
<style scoped>
.booking-documents {
  border-top: 1px solid #dde5dc;
  margin-top: 24px;
  padding-top: 16px;
}
article {
  border: 1px solid #dde5dc;
  border-radius: 12px;
  padding: 16px;
  margin-top: 12px;
}
p {
  color: var(--muted);
}
</style>
