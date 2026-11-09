<script setup>
import { onMounted, onBeforeUnmount, ref } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { useGuestAccountStore } from "@/entities/guest-account";
import { DocumentFiles } from "@/shared/ui";
import { request } from "@/shared/api";
import { dateLabel } from "@/shared/lib";
import { isDemo } from "@/shared/config";

const { t } = useI18n();
const account = useGuestAccountStore(),
  router = useRouter();
const documents = ref([]),
  loading = ref(true),
  error = ref("");
let active = true,
  pending = false;

function signIn() {
  return router.replace({
    path: "/account/login",
    query: { next: "/documents" },
  });
}
async function load() {
  if (pending || !active) return;
  pending = true;
  loading.value = true;
  error.value = "";
  documents.value = [];
  try {
    await account.restore();
    if (!active) return;
    if (!account.authenticated) {
      await signIn();
      return;
    }
    if (isDemo) return;
    const revision = account.revision;
    const result = await request("GET", "/my-documents");
    if (!active || revision !== account.revision) return;
    if (!Array.isArray(result)) throw new Error(t("documents.loadError"));
    documents.value = result;
  } catch (cause) {
    if (!active) return;
    if (cause.status === 401) {
      account.clear();
      await signIn();
      return;
    }
    error.value = t("documents.loadError");
  } finally {
    pending = false;
    if (active) loading.value = false;
  }
}
function refreshOnReturn() {
  if (document.visibilityState === "visible") void load();
}
onMounted(() => {
  void load();
  window.addEventListener("focus", refreshOnReturn);
  document.addEventListener("visibilitychange", refreshOnReturn);
});
onBeforeUnmount(() => {
  active = false;
  documents.value = [];
  window.removeEventListener("focus", refreshOnReturn);
  document.removeEventListener("visibilitychange", refreshOnReturn);
});
</script>

<template>
  <section
    class="guest-documents"
    :aria-label="t('documents.title')"
    :aria-busy="loading"
  >
    <div class="documents-toolbar">
      <span>{{ t("documents.fromProperty") }}</span>
      <button
        type="button"
        class="secondary documents-refresh"
        :disabled="loading"
        @click="load"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.7"
          aria-hidden="true"
        >
          <path
            d="M20 7v5h-5M4 17v-5h5M19 10a7 7 0 0 0-12-3L4 10M5 14a7 7 0 0 0 12 3l3-3"
          />
        </svg>
        {{ t("documents.refresh") }}
      </button>
    </div>
    <div v-if="loading" class="documents-feedback" role="status">
      <span class="documents-spinner" aria-hidden="true" />
      {{ t("documents.loading") }}
    </div>
    <div
      v-else-if="error"
      class="documents-feedback documents-error"
      role="alert"
    >
      <p>{{ error }}</p>
      <button type="button" class="secondary" @click="load">
        {{ t("documents.retry") }}
      </button>
    </div>
    <div v-else-if="isDemo" class="documents-feedback" role="status">
      <p>{{ t("documents.demo") }}</p>
    </div>
    <div
      v-else-if="!documents.length"
      class="documents-feedback documents-empty"
      role="status"
    >
      <strong>{{ t("documents.emptyTitle") }}</strong>
      <p>{{ t("documents.emptyHint") }}</p>
    </div>
    <ul v-else class="documents-list">
      <li v-for="doc in documents" :key="doc.id" class="document-card">
        <div class="document-heading">
          <h2>{{ t(`common.accounting.kinds.${doc.kind}`) }}</h2>
          <span v-if="doc.releasedAt" class="document-date">{{
            dateLabel(doc.releasedAt)
          }}</span>
        </div>
        <p v-if="doc.resortName" class="document-resort">
          {{ doc.resortName }}
        </p>
        <p v-if="doc.start && doc.end" class="document-stay">
          {{ dateLabel(doc.start) }} — {{ dateLabel(doc.end) }}
        </p>
        <p class="document-number">{{ doc.number }}</p>
        <DocumentFiles :path="`/my-documents/${doc.id}`" :number="doc.number" />
      </li>
    </ul>
    <p class="documents-owner-note">{{ t("documents.ownerHint") }}</p>
  </section>
</template>

<style scoped>
.documents-toolbar,
.document-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.documents-toolbar {
  margin-bottom: 12px;
  color: var(--muted);
  font-size: 13px;
}
.documents-refresh {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  flex-shrink: 0;
}
.documents-refresh svg {
  width: 16px;
  height: 16px;
}
.guest-documents button,
.guest-documents :deep(.file-buttons button) {
  min-height: 44px;
  padding: 9px 13px;
  font-size: 14px;
  font-weight: 500;
  border-radius: 12px;
}
.documents-feedback {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 24px 18px;
  border: 1px solid var(--border, #dde5dc);
  border-radius: 16px;
  background: var(--surface, #fff);
  font-size: 14px;
  line-height: 1.5;
  color: var(--muted);
}
.documents-feedback p,
.document-card p {
  margin: 0;
}
.documents-empty {
  display: grid;
  gap: 6px;
}
.documents-empty strong {
  font-size: 16px;
  font-weight: 600;
  color: var(--ink, #273b31);
}
.documents-error p {
  flex: 1 1 220px;
}
.documents-list {
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.document-card {
  display: grid;
  gap: 7px;
  padding: 16px;
  border: 1px solid var(--border, #dde5dc);
  border-radius: 16px;
  background: var(--surface, #fff);
  min-width: 0;
}
.document-heading {
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px 12px;
}
.document-heading h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  line-height: 1.3;
}
.document-date,
.document-stay,
.document-number {
  color: var(--muted);
  font-size: 12px;
  overflow-wrap: anywhere;
}
.document-resort {
  font-size: 14px;
  font-weight: 500;
}
.document-card :deep(.document-files) {
  margin-top: 5px;
}
.document-card :deep(.file-buttons) {
  gap: 6px;
}
.documents-owner-note {
  margin: 16px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
}
.documents-spinner {
  width: 18px;
  height: 18px;
  flex: 0 0 18px;
  border: 2px solid #d6e2d2;
  border-top-color: var(--forest, #244e3e);
  border-radius: 50%;
  animation: documents-spin 0.8s linear infinite;
}
@keyframes documents-spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .documents-spinner {
    animation: none;
  }
}
</style>
