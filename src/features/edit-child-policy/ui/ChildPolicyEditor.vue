<script setup>
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { request } from "@/shared/api";
import { Modal } from "@/shared/ui";
import { money } from "@/shared/lib";
const props = defineProps({ tariffs: { type: Array, required: true } });
const emit = defineEmits(["close", "saved"]);
const { t } = useI18n();
const available = computed(() =>
  props.tariffs.filter((tariff) => tariff.status === "active"),
);
const selectedId = ref(available.value[0]?.id || "");
const selected = computed(() =>
  available.value.find((tariff) => tariff.id === selectedId.value),
);
const enabled = ref(false),
  busy = ref(false),
  error = ref("");
watch(
  selected,
  (tariff) => {
    enabled.value = !!(
      tariff?.childrenUnderTwoFree ?? tariff?.childrenUnderThreeFree
    );
    error.value = "";
  },
  { immediate: true },
);
async function save() {
  if (!selected.value || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const result = await request(
      "PATCH",
      `/tariffs/${encodeURIComponent(selected.value.id)}`,
      {
        version: selected.value.version,
        childrenUnderTwoFree: enabled.value,
      },
    );
    emit("saved", result);
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <Modal
    :title="t('common.children.settingsTitle')"
    :busy="busy"
    @close="emit('close')"
  >
    <form class="editor-form" @submit.prevent="save">
      <p class="field-help">{{ t("common.children.agePolicy") }}</p>
      <template v-if="available.length">
        <label
          >{{ t("common.children.stayOption") }}
          <select v-model="selectedId" :disabled="busy" required>
            <option
              v-for="tariff in available"
              :key="tariff.id"
              :value="tariff.id"
            >
              {{ tariff.name }}
            </option>
          </select>
        </label>
        <p v-if="selected" class="field-help">
          {{
            t("common.children.supplement", {
              price: money(selected.supplement),
            })
          }}
        </p>
        <label class="consent"
          ><input v-model="enabled" type="checkbox" :disabled="busy" />{{
            t("common.pricing.freeUnderTwo")
          }}</label
        >
        <p class="field-help">{{ t("common.pricing.childPolicyHint") }}</p>
        <p class="field-help">{{ t("common.children.futureOnly") }}</p>
      </template>
      <p v-else class="field-help">{{ t("common.children.noOptions") }}</p>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <div class="form-actions">
        <button
          type="button"
          class="secondary"
          :disabled="busy"
          @click="emit('close')"
        >
          {{ t("public.cancel") }}
        </button>
        <button
          v-if="available.length"
          class="primary"
          :disabled="busy || !selected"
        >
          {{ t(busy ? "public.saving" : "common.children.savePolicy") }}
        </button>
      </div>
    </form>
  </Modal>
</template>
