<script setup>
import { ref, watch, onBeforeUnmount } from "vue";
import { useI18n } from "vue-i18n";
import { request } from "@/shared/api";
import { isDemo } from "@/shared/config";
import { DocumentFiles } from "@/shared/ui";
const props = defineProps({
  bookingId: { type: String, required: true },
  completed: Boolean,
  revision: { type: Number, default: 0 },
  manage: Boolean,
  blocked: Boolean,
});
const emit = defineEmits(["busy", "saved"]);
const { t } = useI18n();
const documents = ref([]),
  error = ref(""),
  loading = ref(false),
  busy = ref(false),
  notice = ref("");
let generation = 0;
async function load() {
  const run = ++generation,
    id = props.bookingId;
  documents.value = [];
  error.value = "";
  loading.value = true;
  try {
    if (!isDemo) {
      const result = await request(
        "GET",
        `/bookings/${encodeURIComponent(id)}/documents`,
      );
      if (run === generation) documents.value = result;
    }
  } catch (e) {
    if (run === generation) error.value = e.message;
  } finally {
    if (run === generation) loading.value = false;
  }
}
async function mutate(path, body, released = false) {
  if (busy.value || props.blocked || !props.manage) return;
  const run = generation;
  busy.value = true;
  emit("busy", true);
  error.value = "";
  notice.value = "";
  try {
    await request("POST", path, body);
    if (run !== generation) return;
    await load();
    notice.value = t(
      released ? "common.staffDocuments.sent" : "common.staffDocuments.saved",
    );
    emit("saved");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
    emit("busy", false);
  }
}
function create(kind) {
  return mutate("/accounting/documents", { bookingId: props.bookingId, kind });
}
function action(doc, name) {
  if (
    name === "void" &&
    !window.confirm(t("common.staffDocuments.confirmVoid"))
  )
    return;
  return mutate(
    `/accounting/documents/${encodeURIComponent(doc.id)}/${name}`,
    { version: doc.version },
    name === "release",
  );
}
watch(() => [props.bookingId, props.revision, props.completed], load, {
  immediate: true,
});
onBeforeUnmount(() => {
  generation++;
  emit("busy", false);
});
</script>
<template>
  <section class="booking-documents" :aria-busy="loading || busy">
    <h3>{{ t("common.accounting.documents") }}</h3>
    <p>{{ t("common.accounting.staffDocumentsHint") }}</p>
    <p v-if="isDemo" class="field-help">
      {{ t("common.accounting.demoHint") }}
    </p>
    <template v-else>
      <p v-if="!completed" class="document-prerequisite">
        {{ t("common.staffDocuments.checkoutRequired") }}
      </p>
      <p v-else class="field-help">
        {{ t("common.staffDocuments.releaseRequirements") }}
      </p>
      <p v-if="blocked" class="document-prerequisite">
        {{ t("common.staffDocuments.saveGuestsFirst") }}
      </p>
      <div v-if="manage" class="document-actions">
        <button
          v-for="kind in ['act', 'invoice', 'cash_order']"
          :key="kind"
          class="secondary"
          :disabled="
            busy || loading || blocked || (!completed && kind !== 'cash_order')
          "
          @click="create(kind)"
        >
          {{
            t("common.staffDocuments.prepareKind", {
              kind: t(`common.accounting.kinds.${kind}`),
            })
          }}
        </button>
      </div>
      <p v-if="loading" role="status">
        {{ t("common.staffDocuments.loading") }}
      </p>
      <p v-if="error" role="alert" class="form-error">{{ error }}</p>
      <p v-if="notice" role="status" class="document-notice">{{ notice }}</p>
      <p v-if="!loading && !error && !documents.length">
        {{ t("common.accounting.staffDocumentsEmpty") }}
      </p>
      <article v-for="doc in documents" :key="doc.id">
        <header>
          <h4>
            {{ t(`common.accounting.kinds.${doc.kind}`) }} · {{ doc.number }}
          </h4>
          <span :class="['document-state', doc.state]">{{
            t(`common.accounting.states.${doc.state}`)
          }}</span>
        </header>
        <DocumentFiles
          :path="`/bookings/${bookingId}/documents/${doc.id}`"
          :number="doc.number"
        />
        <p v-if="doc.kind === 'cash_order'" class="field-help">
          {{ t("common.staffDocuments.cashDraft") }}
        </p>
        <div v-if="manage" class="document-actions">
          <button
            v-if="doc.state === 'draft'"
            class="secondary"
            :disabled="busy || blocked"
            @click="action(doc, 'refresh')"
          >
            {{ t("common.accounting.refresh") }}
          </button>
          <button
            v-if="doc.state === 'draft' && doc.kind !== 'cash_order'"
            class="primary"
            :disabled="busy || blocked || !completed"
            @click="action(doc, 'release')"
          >
            {{ t("common.accounting.release") }}
          </button>
          <button
            v-if="doc.state !== 'voided'"
            class="text-button danger"
            :disabled="busy || blocked"
            @click="action(doc, 'void')"
          >
            {{ t("common.accounting.void") }}
          </button>
        </div>
      </article>
    </template>
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
header,
.document-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
header {
  justify-content: space-between;
}
h4 {
  margin: 0;
}
p {
  color: var(--muted);
}
.document-actions {
  margin-top: 12px;
}
.document-actions button {
  min-height: 44px;
  padding: 10px 14px;
  font-size: 0.875rem;
}
.document-state {
  border-radius: 20px;
  background: #f1f3ed;
  padding: 6px 10px;
  font-size: 0.8rem;
}
.document-state.released {
  background: #e3f4e9;
  color: #245e4e;
}
.document-prerequisite {
  padding: 12px;
  background: #fff6e7;
  border-radius: 10px;
}
.document-notice {
  color: #245e4e;
}
</style>
