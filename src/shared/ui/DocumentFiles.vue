<script setup>
import { ref, onBeforeUnmount, nextTick } from "vue";
import { useI18n } from "vue-i18n";
import { requestFile } from "@/shared/api";
import { apiBase } from "@/shared/config";
import Modal from "./Modal.vue";
const props = defineProps({
  path: { type: String, required: true },
  number: { type: String, required: true },
});
const { t } = useI18n();
const busy = ref(""),
  error = ref(""),
  ready = ref(null),
  preview = ref(false),
  saveLink = ref(null);
let active = true;
const types = {
  pdf: "application/pdf",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
};
function clear() {
  if (ready.value) URL.revokeObjectURL(ready.value.url);
  ready.value = null;
}
async function load(ext, show = false) {
  if (busy.value) return;
  busy.value = ext;
  error.value = "";
  preview.value = false;
  try {
    const blob = await requestFile(
      `${props.path}/${ext}/download`,
      apiBase,
      types[ext],
    );
    if (!active) return;
    clear();
    ready.value = {
      url: URL.createObjectURL(blob),
      name: `${props.number}.${ext}`,
      ext,
    };
    if (show) preview.value = true;
    else {
      await nextTick();
      saveLink.value?.click();
    }
  } catch (e) {
    if (active) error.value = e.message;
  } finally {
    if (active) busy.value = "";
  }
}
onBeforeUnmount(() => {
  active = false;
  clear();
});
</script>
<template>
  <div class="document-files">
    <div class="file-buttons">
      <button
        type="button"
        class="secondary"
        :disabled="!!busy"
        @click="load('pdf', true)"
      >
        {{ t("common.accounting.preview") }}
      </button>
      <button
        v-for="ext in ['pdf', 'xlsx']"
        :key="ext"
        type="button"
        class="secondary"
        :disabled="!!busy"
        @click="load(ext)"
      >
        {{ ext.toUpperCase() }}
      </button>
    </div>
    <p v-if="busy" role="status">{{ t("common.accounting.fileLoading") }}</p>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <div v-if="ready" class="file-ready" role="status">
      <span>{{ t("common.accounting.fileReady") }}</span>
      <a ref="saveLink" :href="ready.url" :download="ready.name">{{
        t("common.accounting.downloadFile", { format: ready.ext.toUpperCase() })
      }}</a>
      <a :href="ready.url" target="_blank" rel="noopener">{{
        t("common.accounting.openFile")
      }}</a>
    </div>
    <Modal
      v-if="preview && ready"
      :title="number"
      wide
      @close="preview = false"
    >
      <p class="field-help">{{ t("common.accounting.copyHint") }}</p>
      <p>
        <a :href="ready.url" :download="ready.name">{{
          t("common.accounting.downloadFile", { format: "PDF" })
        }}</a>
        ·
        <a :href="ready.url" target="_blank" rel="noopener">{{
          t("common.accounting.openFile")
        }}</a>
      </p>
      <iframe :src="ready.url" :title="number" class="pdf-preview" />
    </Modal>
  </div>
</template>
<style scoped>
.document-files {
  min-width: 0;
  max-width: 100%;
}
.file-buttons,
.file-ready {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.file-ready {
  padding: 12px 0;
  font-size: 14px;
}
.file-ready span {
  flex-basis: 100%;
  color: var(--muted);
}
a {
  color: var(--forest, #244e3e);
  text-decoration: underline;
  min-height: 32px;
  display: inline-flex;
  align-items: center;
}
.pdf-preview {
  width: 100%;
  height: 65vh;
  border: 1px solid #dde5dc;
  border-radius: 8px;
  background: #f5f5f5;
}
</style>
