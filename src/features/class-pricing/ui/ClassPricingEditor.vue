<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { request } from "@/shared/api";
import { Modal } from "@/shared/ui";
import { categoryNames, money } from "@/shared/lib";
import { classPricingConflicts, classPricingPayload } from "../model/period.js";

const props = defineProps({ resort: { type: Object, required: true } });
const emit = defineEmits(["close", "saved"]);
const { t } = useI18n();
const category = ref("standard"),
  preview = ref(null),
  loading = ref(false),
  busy = ref(false);
const error = ref("");
const period = reactive({ label: "", start: "", end: "", price: "" });
const conflicts = computed(() =>
  classPricingConflicts(preview.value?.rooms || [], period),
);
const payload = computed(() => classPricingPayload(preview.value, period));
let generation = 0;
async function reload() {
  const run = ++generation;
  loading.value = true;
  error.value = "";
  preview.value = null;
  try {
    const result = await request(
      "GET",
      `/resorts/${props.resort.id}/class-pricing?category=${category.value}`,
    );
    if (run === generation) preview.value = result;
  } catch (e) {
    if (run === generation) error.value = e.message;
  } finally {
    if (run === generation) loading.value = false;
  }
}
async function submit() {
  if (!payload.value || conflicts.value.length || busy.value || loading.value)
    return;
  busy.value = true;
  error.value = "";
  try {
    const result = await request(
      "POST",
      `/resorts/${props.resort.id}/class-pricing`,
      payload.value,
    );
    emit("saved", result);
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
watch(category, reload, { immediate: true });
onBeforeUnmount(() => generation++);
</script>

<template>
  <Modal
    :title="t('common.classPricing.title')"
    :busy="busy"
    @close="emit('close')"
  >
    <form class="editor-form class-pricing" @submit.prevent="submit">
      <p>
        <strong>{{ resort.name }}</strong>
      </p>
      <p class="field-help">{{ t("common.classPricing.scopeHelp") }}</p>
      <label
        >{{ t("common.classPricing.category") }}
        <select v-model="category" :disabled="busy">
          <option v-for="(name, key) in categoryNames" :key="key" :value="key">
            {{ name }}
          </option>
        </select>
      </label>
      <p v-if="loading" role="status">{{ t("common.classPricing.loading") }}</p>
      <p v-else-if="preview && !preview.roomCount" role="status">
        {{ t("common.classPricing.empty") }}
      </p>
      <div v-if="preview?.roomCount" class="class-pricing-summary">
        <strong>{{
          t("common.classPricing.affected", { count: preview.roomCount })
        }}</strong>
        <details>
          <summary>{{ t("common.classPricing.showRooms") }}</summary>
          <ul>
            <li v-for="room in preview.rooms" :key="room.id">
              № {{ room.number }} · {{ room.title }}
              <span v-if="room.status === 'maintenance'">
                — {{ t("common.classPricing.maintenance") }}</span
              >
            </li>
          </ul>
        </details>
      </div>
      <label
        >{{ t("common.classPricing.label")
        }}<input
          v-model="period.label"
          required
          maxlength="80"
          :disabled="busy"
      /></label>
      <div class="form-grid">
        <label
          >{{ t("common.classPricing.start")
          }}<input v-model="period.start" type="date" required :disabled="busy"
        /></label>
        <label
          >{{ t("common.classPricing.end")
          }}<input
            v-model="period.end"
            type="date"
            required
            :min="period.start || undefined"
            :disabled="busy"
        /></label>
      </div>
      <small>{{ t("common.classPricing.endHelp") }}</small>
      <label
        >{{ t("common.classPricing.price")
        }}<input
          v-model="period.price"
          type="number"
          required
          min="0"
          max="10000000"
          step="1"
          :disabled="busy"
      /></label>
      <p v-if="payload" class="field-help">
        {{
          t("common.classPricing.priceSummary", {
            price: money(payload.period.price),
            count: preview.roomCount,
          })
        }}
      </p>
      <p v-if="conflicts.length" role="alert" class="form-error">
        {{
          t("common.classPricing.conflict", {
            rooms: conflicts.map((room) => room.number).join(", "),
          })
        }}
      </p>
      <p class="field-help">{{ t("common.classPricing.manageHelp") }}</p>
      <p v-if="error" role="alert" class="form-error">{{ error }}</p>
      <button
        v-if="error"
        type="button"
        class="secondary"
        :disabled="busy || loading"
        @click="reload"
      >
        {{ t("common.classPricing.reload") }}
      </button>
      <div class="form-actions">
        <button
          type="button"
          class="secondary"
          :disabled="busy"
          @click="emit('close')"
        >
          {{ t("common.classPricing.cancel") }}
        </button>
        <button
          class="primary"
          :disabled="busy || loading || !payload || conflicts.length"
        >
          {{
            busy
              ? t("common.classPricing.saving")
              : t("common.classPricing.apply", {
                  count: preview?.roomCount || 0,
                })
          }}
        </button>
      </div>
    </form>
  </Modal>
</template>

<style scoped>
.class-pricing-summary {
  display: grid;
  gap: 12px;
  padding: 16px;
  border-radius: 14px;
  background: #f1f5ed;
}
.class-pricing-summary summary {
  cursor: pointer;
}
.class-pricing-summary ul {
  max-height: 160px;
  overflow-y: auto;
  padding-left: 20px;
}
.class-pricing .form-error {
  overflow-wrap: anywhere;
}
</style>
