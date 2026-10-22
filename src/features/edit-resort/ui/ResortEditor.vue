<script setup>
import { useI18n } from "vue-i18n";
import { reactive, ref } from "vue";
import { Modal, GeoMap, MediaEditor } from "@/shared/ui";
import { useEditor } from "@/shared/api/use-editor.js";
const { t } = useI18n();
const props = defineProps({ item: Object });
const emit = defineEmits(["close", "saved"]);
const mediaBusy = ref(false);
const form = reactive({
  media: [],
  amenities: [],
  name: "",
  category: "wellness",
  resortClass: "standard",
  checkInTime: "14:00",
  timeZone: "Asia/Almaty",
  city: t("staff.saryagash"),
  address: "",
  subtitle: "",
  description: "",
  feature: t("staff.rest"),
  lat: 41.385,
  lng: 69.061,
  status: "draft",
  ...props.item,
  media: JSON.parse(JSON.stringify(props.item?.media || [])),
  amenities: (props.item?.amenities || []).join("\n"),
});
const { busy, error, save } = useEditor("resorts", props.item, emit);
</script>
<template>
  <Modal
    :title="item ? t('staff.resortSettings') : t('staff.newResort')"
    wide
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
      <div class="form-section">
        <span class="section-number">01</span>
        <h3>{{ t("staff.basicInformation") }}</h3>
      </div>
      <div class="form-grid">
        <label
          >{{ t("staff.category")
          }}<select v-model="form.category">
            <option value="wellness">{{ t("staff.wellness") }}</option>
            <option value="family">{{ t("staff.family") }}</option>
            <option value="premium">{{ t("staff.premium") }}</option>
            <option value="nature">{{ t("staff.nature") }}</option>
          </select></label
        >
        <label
          >{{ t("staff.resortClass")
          }}<select v-model="form.resortClass">
            <option value="standard">{{ t("staff.standard") }}</option>
            <option value="comfort">{{ t("staff.comfort") }}</option>
            <option value="premium">{{ t("staff.premium") }}</option>
          </select></label
        >
        <label
          >{{ t("staff.checkInTime")
          }}<input v-model="form.checkInTime" type="time" required
        /></label>
        <label
          >{{ t("staff.timeZone")
          }}<select v-model="form.timeZone">
            <option value="Asia/Almaty">
              {{ t("staff.kazakhstanTimeZone") }}
            </option>
          </select></label
        >
        <label class="span-2"
          >{{ t("staff.name")
          }}<input
            v-model="form.name"
            required
            maxlength="100"
            :placeholder="t('staff.resortNamePlaceholder')" /></label
        ><label
          >{{ t("staff.city")
          }}<input v-model="form.city" required maxlength="80" /></label
        ><label
          >{{ t("staff.address")
          }}<input
            v-model="form.address"
            required
            maxlength="200"
            :placeholder="t('staff.addressPlaceholder')" /></label
        ><label class="span-2"
          >{{ t("staff.shortDescription")
          }}<input
            v-model="form.subtitle"
            maxlength="160"
            :placeholder="t('staff.subtitlePlaceholder')" /></label
        ><label class="span-2"
          >{{ t("staff.description")
          }}<textarea
            v-model="form.description"
            rows="3"
            maxlength="2000"
          ></textarea></label
        ><label
          >{{ t("staff.mainService")
          }}<input v-model="form.feature" maxlength="80" required /></label
        ><label
          >{{ t("staff.visibility")
          }}<select v-model="form.status">
            <option value="draft">{{ t("staff.draft") }}</option>
            <option value="published">{{ t("staff.published") }}</option>
          </select></label
        >
      </div>
      <p class="field-help">
        {{ t("staff.publishHint") }}
      </p>
      <div class="form-section">
        <span class="section-number">02</span>
        <h3>{{ t("staff.mapLocation") }}</h3>
      </div>
      <GeoMap
        editable
        :lat="Number(form.lat)"
        :lng="Number(form.lng)"
        @location="Object.assign(form, $event)"
      />
      <div class="form-grid">
        <label
          >{{ t("staff.latitude")
          }}<input
            v-model.number="form.lat"
            type="number"
            step="any"
            min="-90"
            max="90"
            required /></label
        ><label
          >{{ t("staff.longitude")
          }}<input
            v-model.number="form.lng"
            type="number"
            step="any"
            min="-180"
            max="180"
            required
        /></label>
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
        :resort-id="item?.id"
        @busy="mediaBusy = $event"
      />
      <p v-if="error" role="alert" class="form-error">{{ error }}</p>
      <div class="form-actions">
        <button
          class="secondary"
          type="button"
          :disabled="busy || mediaBusy"
          @click="emit('close')"
        >
          {{ t("staff.cancel") }}</button
        ><button class="primary" :disabled="busy || mediaBusy">
          {{ busy ? t("staff.saving") : t("staff.saveResort") }}
        </button>
      </div>
    </form></Modal
  >
</template>
