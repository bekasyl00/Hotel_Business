<script setup>
import { useI18n } from "vue-i18n";
import { reactive, ref } from "vue";
import { Modal, MediaEditor } from "@/shared/ui";
import { useEditor } from "@/shared/api/use-editor.js";
import { validatePricePeriods } from "@/entities/booking";
import { categoryNames } from "@/shared/lib";
const { t } = useI18n();
const props = defineProps({ item: Object, resortId: String });
const emit = defineEmits(["close", "saved"]);
const mediaBusy = ref(false);
const form = reactive({
  media: [],
  amenities: [],
  resortId: props.resortId,
  number: "",
  category: "standard",
  title: t("staff.standard"),
  description: "",
  capacity: 2,
  area: 22,
  beds: t("staff.twinBeds"),
  price: 24000,
  status: "active",
  ...props.item,
  media: JSON.parse(JSON.stringify(props.item?.media || [])),
  pricePeriods: JSON.parse(JSON.stringify(props.item?.pricePeriods || [])),
  amenities: (props.item?.amenities || []).join("\n"),
});
const { busy, error, save } = useEditor("rooms", props.item, emit);
async function saveRoom() {
  error.value = validatePricePeriods(form.pricePeriods);
  if (error.value || mediaBusy.value) return;
  await save({
    ...form,
    amenities: form.amenities
      .split("\n")
      .map((v) => v.trim())
      .filter(Boolean),
  });
}
</script>
<template>
  <Modal
    :title="item ? t('staff.editRoom') : t('staff.addRoom')"
    :busy="busy || mediaBusy"
    @close="emit('close')"
    ><form class="editor-form" @submit.prevent="saveRoom">
      <p class="field-help">
        {{ t("staff.physicalRoomHint") }}
      </p>
      <div class="form-grid">
        <label
          >{{ t("staff.roomNumber")
          }}<input
            v-model="form.number"
            required
            maxlength="20"
            :placeholder="t('staff.roomNumberPlaceholder')" /></label
        ><label
          >{{ t("staff.category")
          }}<select
            v-model="form.category"
            @change="form.title = categoryNames[form.category]"
          >
            <option
              v-for="(title, key) in categoryNames"
              :key="key"
              :value="key"
            >
              {{ title }}
            </option>
          </select></label
        ><label class="span-2"
          >{{ t("staff.name")
          }}<input v-model="form.title" required maxlength="80" /></label
        ><label
          >{{ t("staff.capacity")
          }}<input
            v-model.number="form.capacity"
            type="number"
            min="1"
            max="4"
            required /></label
        ><label
          >{{ t("staff.areaSquareMetres")
          }}<input
            v-model.number="form.area"
            type="number"
            min="5"
            max="500"
            step="1"
            required /></label
        ><label class="span-2"
          >{{ t("staff.beds")
          }}<input v-model="form.beds" required maxlength="120" /></label
        ><label
          >{{ t("staff.nightlyPriceKzt")
          }}<input
            v-model.number="form.price"
            type="number"
            min="0"
            max="10000000"
            step="1"
            required /></label
        ><label
          >{{ t("staff.status")
          }}<select v-model="form.status">
            <option value="active">{{ t("staff.active") }}</option>
            <option value="maintenance">{{ t("staff.maintenance") }}</option>
          </select></label
        >
      </div>
      <fieldset class="pricing-fields">
        <legend>{{ t("common.pricing.periods") }}</legend>
        <p class="field-help">{{ t("common.pricing.periodHint") }}</p>
        <div
          v-for="(period, index) in form.pricePeriods"
          :key="index"
          class="price-period-row"
        >
          <label
            >{{ t("common.pricing.label")
            }}<input v-model="period.label" maxlength="80" required
          /></label>
          <label
            >{{ t("common.pricing.start")
            }}<input v-model="period.start" type="date" required
          /></label>
          <label
            >{{ t("common.pricing.end")
            }}<input
              v-model="period.end"
              type="date"
              :min="period.start"
              required
          /></label>
          <label
            >{{ t("staff.nightlyPriceKzt")
            }}<input
              v-model.number="period.price"
              type="number"
              min="0"
              max="10000000"
              step="1"
              required
          /></label>
          <button
            type="button"
            class="secondary"
            :disabled="busy"
            @click="form.pricePeriods.splice(index, 1)"
          >
            {{ t("common.pricing.remove") }}
          </button>
        </div>
        <button
          type="button"
          class="secondary"
          :disabled="busy || form.pricePeriods.length >= 60"
          @click="
            form.pricePeriods.push({
              label: '',
              start: '',
              end: '',
              price: form.price,
            })
          "
        >
          {{ t("common.pricing.add") }}
        </button>
      </fieldset>
      <label
        >{{ t("staff.amenitiesLines")
        }}<textarea
          v-model="form.amenities"
          maxlength="1500"
          rows="3"
        ></textarea>
      </label>
      <MediaEditor
        v-model="form.media"
        :resort-id="resortId"
        @busy="mediaBusy = $event"
      />
      <label
        >{{ t("staff.roomDescription")
        }}<textarea
          v-model="form.description"
          rows="4"
          maxlength="3000"
        ></textarea>
      </label>
      <p v-if="error" role="alert" class="form-error">{{ error }}</p>
      <div class="form-actions">
        <button
          type="button"
          class="secondary"
          @click="emit('close')"
          :disabled="busy || mediaBusy"
        >
          {{ t("staff.cancel") }}</button
        ><button class="primary" :disabled="busy || mediaBusy">
          {{ busy ? t("staff.saving") : t("staff.saveRoom") }}
        </button>
      </div>
    </form></Modal
  >
</template>
