<script setup>
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { request, requestFile } from "@/shared/api";
import { apiBase, isDemo } from "@/shared/config";
const { t } = useI18n(),
  documents = ref([]),
  error = ref("");
onMounted(async () => {
  if (isDemo) return;
  try {
    documents.value = await request("GET", "/my-documents");
  } catch (e) {
    error.value = e.message;
  }
});
async function download(doc, ext) {
  error.value = "";
  try {
    const blob = await requestFile(
      `/my-documents/${doc.id}/${ext}/download`,
      apiBase,
      ext === "pdf"
        ? "application/pdf"
        : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    );
    const url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download = doc.number + "." + ext;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) {
    error.value = e.message;
  }
}
</script>
<template>
  <section class="guest-documents">
    <h2>{{ t("common.accounting.documents") }}</h2>
    <p>{{ t("common.accounting.guestHint") }}</p>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <article v-for="doc in documents" :key="doc.id">
      <div>
        <strong>{{ t(`common.accounting.kinds.${doc.kind}`) }}</strong
        ><small>{{ doc.number }}</small>
      </div>
      <button class="secondary" @click="download(doc, 'pdf')">PDF</button
      ><button class="secondary" @click="download(doc, 'xlsx')">XLSX</button>
    </article>
  </section>
</template>
<style scoped>
.guest-documents {
  margin: 32px 0;
  border: 1px solid #dde5dc;
  border-radius: 14px;
  padding: 20px;
}
.guest-documents p {
  color: var(--muted);
}
article {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 16px 0;
  border-top: 1px solid #dde5dc;
}
article div {
  flex: 1;
}
small {
  display: block;
  margin-top: 6px;
}
button {
  min-height: 44px;
}
</style>
