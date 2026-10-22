<script setup>
import { useI18n } from "vue-i18n";
import { reactive, ref } from "vue";
import { Modal, MediaEditor } from "@/shared/ui";
import { useEditor } from "@/shared/api/use-editor.js";
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
  amenities: (props.item?.amenities || []).join("\n"),
});
const { busy, error, save } = useEditor("rooms", props.item, emit);
</script>
<template>
  <Modal
    :title="item ? t('staff.editRoom') : t('staff.addRoom')"
    :busy="busy || mediaBusy"
    @close="emit('close')"
    ><form
      class="editor-form"
      @submit.prevent="
        !mediaBusy &&
        save({
          ...form,
          amenities: form.amenities
            .split('\n')
            .map((v) => v.trim())
            .filter(Boolean),
        })
      "
    >
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
