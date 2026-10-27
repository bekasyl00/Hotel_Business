<script setup>
import { useI18n } from "vue-i18n";
const { t, locale } = useI18n();
import { ref, onMounted, watch } from "vue";
import { requestFile } from "@/shared/api";
import { isDemo, apiBase } from "@/shared/config";
import { isNative, shareNativeFile } from "@/shared/native";
import {
  generateDemoReceiptPdf,
  receiptFilename,
  downloadBlob,
} from "../model/pdf.js";
const props = defineProps({ bundle: { type: Object, required: true } });
const busy = ref(false),
  error = ref(""),
  notice = ref("");
let filePromise;
function prepare() {
  if (!filePromise)
    filePromise = (
      isDemo
        ? generateDemoReceiptPdf(props.bundle, locale.value)
        : requestFile(
            `/receipts/${encodeURIComponent(props.bundle.receipt.paymentId)}/pdf`,
            apiBase,
          )
    )
      .then(
        (blob) =>
          new File([blob], receiptFilename(props.bundle.receipt.number), {
            type: "application/pdf",
          }),
      )
      .catch((e) => {
        filePromise = null;
        throw e;
      });
  return filePromise;
}
async function save(share = false) {
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    const file = await prepare();
    if (isNative()) {
      await shareNativeFile(file, t("public.tynysDemoReceipt"));
      notice.value = t("common.mobile.saveFile");
      return;
    }
    if (share && navigator.share && navigator.canShare?.({ files: [file] })) {
      try {
        await navigator.share({
          files: [file],
          title: t("public.tynysDemoReceipt"),
        });
        notice.value = t("public.theFileWasPassedToYourDeviceShareMenu");
        return;
      } catch (e) {
        if (e.name === "AbortError") {
          notice.value = t("public.sharingCancelled");
          return;
        }
      }
    }
    downloadBlob(file, file.name);
    notice.value = share
      ? t("public.thisBrowserCouldNotOpenFileSharingThePdfWasDownloadedAnd")
      : t("public.pdfDownloadedThisIsADemoReceiptNotAKaspiReceipt");
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
onMounted(() => prepare().catch(() => {}));
watch(locale, () => {
  filePromise = null;
  prepare().catch(() => {});
});
</script>
<template>
  <div class="receipt-actions">
    <div>
      <button class="primary" :disabled="busy" @click="save(false)">
        {{ busy ? t("public.preparingPdf") : t("public.downloadPdf") }}</button
      ><button class="secondary" :disabled="busy" @click="save(true)">
        {{ t("public.shareFile") }}
      </button>
    </div>
    <p v-if="!isDemo" class="field-help">{{ t("public.serverPdfLanguage") }}</p>
    <p v-if="notice" role="status" class="field-help">{{ notice }}</p>
    <p v-if="error" role="alert" class="form-error">{{ error }}</p>
  </div>
</template>
