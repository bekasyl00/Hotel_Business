<script setup>
import { ref, watch, onBeforeUnmount } from "vue";
import { useI18n } from "vue-i18n";
import { request } from "@/shared/api";
import { isDemo } from "@/shared/config";
const props = defineProps({ resortId: { type: String, required: true } });
const emit = defineEmits(["saved", "busy"]);
const { t } = useI18n();
const form = ref(null),
  loading = ref(false),
  busy = ref(false),
  error = ref(""),
  conflict = ref(false),
  notice = ref("");
const fields = [
  ["supplier", 160],
  ["bin", 12],
  ["address", 240],
  ["iban", 20],
  ["bank", 100],
  ["bik", 11],
  ["director", 100],
  ["accountant", 100],
];
let generation = 0;
watch([loading, busy], () => emit("busy", loading.value || busy.value));
async function load() {
  const run = ++generation;
  form.value = null;
  error.value = "";
  notice.value = "";
  conflict.value = false;
  if (isDemo) return;
  loading.value = true;
  try {
    const data = await request(
      "GET",
      `/staff-profile/company/${encodeURIComponent(props.resortId)}`,
    );
    if (run === generation)
      form.value = {
        supplier: "",
        bin: "",
        address: "",
        iban: "",
        bank: "",
        bik: "",
        director: "",
        accountant: "",
        vatMode: "no_vat",
        vatRate: "0",
        ...data,
      };
  } catch (e) {
    if (run === generation) error.value = e.message;
  } finally {
    if (run === generation) loading.value = false;
  }
}
async function save() {
  if (busy.value || !form.value) return;
  busy.value = true;
  error.value = "";
  notice.value = "";
  conflict.value = false;
  try {
    const { resortId, ...body } = form.value;
    body.iban = body.iban.trim().toUpperCase();
    body.bik = body.bik.trim().toUpperCase();
    const result = await request(
      "PATCH",
      `/staff-profile/company/${encodeURIComponent(props.resortId)}`,
      body,
    );
    form.value = { ...form.value, ...result };
    notice.value = t("common.staffProfile.companySaved");
    emit("saved", result);
  } catch (e) {
    error.value = e.message;
    conflict.value = e.status === 409;
  } finally {
    busy.value = false;
  }
}
watch(() => props.resortId, load, { immediate: true });
onBeforeUnmount(() => {
  generation++;
  emit("busy", false);
});
</script>
<template>
  <div class="company-details" :aria-busy="loading || busy">
    <p v-if="isDemo" class="field-help">
      {{ t("common.accounting.demoHint") }}
    </p>
    <p v-else-if="loading" role="status">
      {{ t("common.staffProfile.loading") }}
    </p>
    <form v-else-if="form" class="editor-form" @submit.prevent="save">
      <p class="field-help">{{ t("common.staffProfile.companyHint") }}</p>
      <fieldset :disabled="busy">
        <legend class="company-sr-only">
          {{ t("common.staffProfile.companyTitle") }}
        </legend>
        <div class="form-grid">
          <label v-for="[key, max] in fields" :key="key"
            >{{ t(`common.accounting.fields.${key}`)
            }}<input
              v-model.trim="form[key]"
              :required="['supplier', 'bin', 'address'].includes(key)"
              :maxlength="max"
              :inputmode="key === 'bin' ? 'numeric' : undefined"
              :pattern="
                key === 'bin'
                  ? '[0-9]{12}'
                  : key === 'iban'
                    ? '[Kk][Zz][A-Za-z0-9]{18}'
                    : key === 'bik'
                      ? '[A-Za-z0-9]{8}([A-Za-z0-9]{3})?'
                      : undefined
              "
              :autocomplete="
                ['supplier', 'address'].includes(key) ? 'off' : undefined
              "
          /></label>
          <label
            >{{ t("common.accounting.vat")
            }}<select
              v-model="form.vatMode"
              @change="
                form.vatRate = form.vatMode === 'no_vat' ? '0' : form.vatRate
              "
            >
              <option value="no_vat">{{ t("common.accounting.noVat") }}</option>
              <option value="included">
                {{ t("common.accounting.vatIncluded") }}
              </option>
            </select></label
          >
          <label v-if="form.vatMode === 'included'"
            >{{ t("common.accounting.vatRate")
            }}<input
              v-model="form.vatRate"
              type="number"
              min="0.01"
              max="100"
              step="0.01"
              required
          /></label>
        </div>
      </fieldset>
      <p class="field-help">{{ t("common.accounting.companyHint") }}</p>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <p v-if="notice" class="company-notice" role="status">{{ notice }}</p>
      <div class="form-actions">
        <button
          v-if="conflict"
          type="button"
          class="secondary"
          :disabled="busy"
          @click="load"
        >
          {{ t("common.staffProfile.reload") }}</button
        ><button class="primary" :disabled="busy || conflict">
          {{ t(busy ? "staff.saving" : "common.staffProfile.saveCompany") }}
        </button>
      </div>
    </form>
    <div v-else-if="error" role="alert">
      <p class="form-error">{{ error }}</p>
      <button class="secondary" @click="load">
        {{ t("common.staffProfile.retry") }}
      </button>
    </div>
  </div>
</template>
<style scoped>
.company-details fieldset {
  border: 0;
  margin: 0;
  padding: 0;
  min-width: 0;
}
.company-details input,
.company-details select {
  width: 100%;
  box-sizing: border-box;
  min-height: 44px;
}
.company-notice {
  color: #245e4e;
}
.company-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}
</style>
