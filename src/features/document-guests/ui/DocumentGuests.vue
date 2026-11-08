<script setup>
import { ref, watch, onBeforeUnmount } from "vue";
import { useI18n } from "vue-i18n";
import { request } from "@/shared/api";
import { isDemo } from "@/shared/config";
import {
  documentGuestsForm,
  documentGuestsPayload,
  validateDocumentGuests,
} from "../model/form.js";

const props = defineProps({
  bookingId: { type: String, required: true },
  guestName: { type: String, default: "" },
});
const emit = defineEmits(["saved", "busy"]);
const { t } = useI18n();
const form = ref(null),
  loading = ref(false),
  saving = ref(false),
  error = ref(""),
  saved = ref(false),
  conflict = ref(false);
let generation = 0;
const optionalFields = ["phone", "iban", "bank", "bik"];
const limits = { phone: 32, iban: 20, bank: 100, bik: 11 };

async function load() {
  const run = ++generation;
  form.value = null;
  error.value = "";
  saved.value = false;
  conflict.value = false;
  saving.value = false;
  emit("busy", false);
  if (isDemo) return;
  loading.value = true;
  try {
    const result = await request(
      "GET",
      `/bookings/${encodeURIComponent(props.bookingId)}/document-guests`,
    );
    if (run === generation)
      form.value = documentGuestsForm(result, props.guestName);
  } catch (e) {
    if (run === generation)
      error.value =
        e.message === "invalidResponse"
          ? t("common.error.invalidResponse")
          : e.message;
  } finally {
    if (run === generation) loading.value = false;
  }
}
async function save() {
  saved.value = false;
  error.value = "";
  conflict.value = false;
  const invalid = validateDocumentGuests(form.value);
  if (invalid) {
    error.value = t(`common.documentGuests.${invalid.key}`, invalid);
    return;
  }
  const run = generation;
  saving.value = true;
  emit("busy", true);
  try {
    const result = await request(
      "PUT",
      `/bookings/${encodeURIComponent(props.bookingId)}/document-guests`,
      documentGuestsPayload(form.value),
    );
    if (run !== generation) return;
    form.value = documentGuestsForm(result);
    saved.value = true;
    emit("saved", {
      bookingId: props.bookingId,
      version: result.version,
      complete: result.complete,
    });
  } catch (e) {
    if (run === generation) {
      conflict.value = e.status === 409;
      error.value = conflict.value
        ? t("common.documentGuests.conflict")
        : e.message;
    }
  } finally {
    if (run === generation) {
      saving.value = false;
      emit("busy", false);
    }
  }
}
watch(() => props.bookingId, load, { immediate: true });
onBeforeUnmount(() => {
  generation++;
  form.value = null;
  emit("busy", false);
});
</script>
<template>
  <section class="document-guests">
    <h3>{{ t("common.documentGuests.title") }}</h3>
    <p class="field-help">{{ t("common.documentGuests.hint") }}</p>
    <p v-if="isDemo" class="field-help" role="status">
      {{ t("common.documentGuests.demoUnavailable") }}
    </p>
    <p v-else-if="loading" role="status">
      {{ t("common.documentGuests.loading") }}
    </p>
    <form
      v-else-if="form"
      class="editor-form"
      autocomplete="off"
      @submit.prevent="save"
      @input="saved = false"
    >
      <p class="field-help">{{ t("common.documentGuests.requiredHint") }}</p>
      <fieldset
        v-for="(guest, index) in form.guests"
        :key="index"
        :disabled="saving"
        class="document-guest-card"
      >
        <legend>
          {{ t("common.documentGuests.guest", { number: index + 1 }) }}
        </legend>
        <div class="document-guest-grid">
          <label
            >{{ t("common.documentGuests.fullName")
            }}<input
              v-model="guest.fullName"
              maxlength="160"
              autocomplete="off"
          /></label>
          <label
            >{{ t("common.documentGuests.iin")
            }}<input
              v-model="guest.iin"
              inputmode="numeric"
              minlength="12"
              maxlength="12"
              pattern="[0-9]{12}"
              autocomplete="off"
              spellcheck="false"
          /></label>
          <label class="document-guest-address"
            >{{ t("common.documentGuests.address")
            }}<input v-model="guest.address" maxlength="240" autocomplete="off"
          /></label>
        </div>
        <details class="document-guest-optional">
          <summary>{{ t("common.documentGuests.optional") }}</summary>
          <div class="document-guest-grid">
            <label v-for="field in optionalFields" :key="field"
              >{{ t(`common.documentGuests.${field}`)
              }}<input
                v-model="guest[field]"
                :maxlength="limits[field]"
                :type="field === 'phone' ? 'tel' : 'text'"
                autocomplete="off"
            /></label>
          </div>
        </details>
      </fieldset>
      <label
        >{{ t("common.documentGuests.buyer") }}
        <select v-model="form.buyerIndex" :disabled="saving">
          <option :value="null">
            {{ t("common.documentGuests.chooseBuyer") }}
          </option>
          <option
            v-for="(guest, index) in form.guests"
            :key="index"
            :value="index"
          >
            {{
              guest.fullName ||
              t("common.documentGuests.guest", { number: index + 1 })
            }}
          </option>
        </select>
      </label>
      <p class="field-help">
        {{ t("common.documentGuests.savedDocumentHint") }}
      </p>
      <p v-if="saved" class="document-guests-saved" role="status">
        {{ t("common.documentGuests.saved") }}
      </p>
      <div class="document-guests-actions">
        <button class="primary" :disabled="saving">
          {{
            t(
              saving
                ? "common.documentGuests.saving"
                : "common.documentGuests.save",
            )
          }}
        </button>
        <button
          v-if="conflict"
          class="secondary"
          type="button"
          :disabled="saving"
          @click="load"
        >
          {{ t("common.documentGuests.reload") }}
        </button>
      </div>
    </form>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <button
      v-if="!isDemo && !form && !loading"
      class="secondary"
      type="button"
      @click="load"
    >
      {{ t("common.documentGuests.retry") }}
    </button>
  </section>
</template>
<style scoped>
.document-guests {
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid #dce4de;
}
.document-guests h3 {
  margin: 0 0 0.6rem;
}
.document-guest-card {
  margin: 0;
  padding: 1rem;
  border: 1px solid #dce4de;
  border-radius: 14px;
  min-width: 0;
}
.document-guest-card legend {
  padding: 0 0.4rem;
  font-weight: 700;
}
.document-guest-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.85rem;
}
.document-guest-grid label {
  min-width: 0;
}
.document-guest-grid input {
  min-width: 0;
  width: 100%;
  box-sizing: border-box;
}
.document-guest-address {
  grid-column: 1/-1;
}
.document-guest-optional {
  margin-top: 1rem;
}
.document-guest-optional summary {
  cursor: pointer;
  min-height: 32px;
  color: #315f4b;
  font-size: 0.875rem;
}
.document-guest-optional .document-guest-grid {
  margin-top: 0.5rem;
}
.document-guests-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}
.document-guests-saved {
  color: #215b49;
}
@media (max-width: 560px) {
  .document-guest-grid {
    grid-template-columns: 1fr;
  }
  .document-guests-actions button {
    width: 100%;
  }
}
</style>
