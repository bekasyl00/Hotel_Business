<script setup>
import { useI18n } from "vue-i18n";
import { reactive } from "vue";
import { Modal } from "@/shared/ui";
import { useEditor } from "@/shared/api/use-editor.js";
const { t } = useI18n();
const props = defineProps({ item: Object, resortId: String });
const emit = defineEmits(["close", "saved"]);
const form = reactive({
  resortId: props.resortId,
  name: "",
  description: "",
  supplement: 0,
  priceKind: "regular",
  discountPercent: 0,
  status: "active",
  ...props.item,
  features: props.item?.features.join("\n") || "",
});
const { busy, error, save } = useEditor("tariffs", props.item, emit);
</script>
<template>
  <Modal
    :title="item ? t('staff.editTariff') : t('staff.addTariff')"
    :busy="busy"
    @close="emit('close')"
    ><form
      class="editor-form"
      @submit.prevent="
        save({
          ...form,
          discountPercent:
            form.priceKind === 'discount' ? form.discountPercent : 0,
        })
      "
    >
      <label
        >{{ t("staff.name")
        }}<input
          v-model="form.name"
          required
          maxlength="80"
          :placeholder="t('staff.tariffNamePlaceholder')" /></label
      ><label
        >{{ t("staff.description")
        }}<textarea
          v-model="form.description"
          rows="2"
          maxlength="400"
        ></textarea>
      </label>
      <div class="form-grid">
        <label
          >{{ t("staff.priceKind")
          }}<select v-model="form.priceKind">
            <option value="regular">{{ t("staff.regularPrice") }}</option>
            <option value="discount">{{ t("staff.discountPrice") }}</option>
          </select></label
        >
        <label v-if="form.priceKind === 'discount'"
          >{{ t("staff.discountPercent")
          }}<input
            v-model.number="form.discountPercent"
            type="number"
            min="1"
            max="90"
            required
        /></label>
        <label
          >{{ t("staff.supplementKzt")
          }}<input
            v-model.number="form.supplement"
            type="number"
            min="0"
            max="10000000"
            step="1"
            required /></label
        ><label
          >{{ t("staff.status")
          }}<select v-model="form.status">
            <option value="active">{{ t("staff.active") }}</option>
            <option value="disabled">{{ t("staff.disabled") }}</option>
          </select></label
        >
      </div>
      <label
        >{{ t("staff.includedLines")
        }}<textarea
          v-model="form.features"
          rows="4"
          maxlength="400"
          :placeholder="t('staff.featuresPlaceholder')"
        ></textarea>
      </label>
      <p class="field-help">
        {{ t("staff.discountHint") }}
      </p>
      <p v-if="error" role="alert" class="form-error">{{ error }}</p>
      <div class="form-actions">
        <button
          type="button"
          class="secondary"
          :disabled="busy"
          @click="emit('close')"
        >
          {{ t("staff.cancel") }}</button
        ><button class="primary" :disabled="busy">
          {{ busy ? t("staff.saving") : t("staff.saveTariff") }}
        </button>
      </div>
    </form></Modal
  >
</template>
