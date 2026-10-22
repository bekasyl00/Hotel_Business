<script setup>
import { useI18n } from "vue-i18n";
import { ref } from "vue";
import { request } from "../api/index.js";
import { isDemo } from "../config/index.js";
const { t } = useI18n();
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  resortId: String,
});
const emit = defineEmits(["update:modelValue", "busy"]);
const error = ref(""),
  uploading = ref(false),
  url = ref(""),
  kind = ref("image"),
  alt = ref("");
function append(item) {
  emit("update:modelValue", [...props.modelValue, item]);
}
function addUrl() {
  error.value = "";
  if (!/^(https:\/\/|\/assets\/|\/media\/)/.test(url.value)) {
    error.value = t("staff.mediaUrlError");
    return;
  }
  if (props.modelValue.length >= 12) {
    error.value = t("staff.mediaLimit");
    return;
  }
  append({ kind: kind.value, url: url.value.trim(), alt: alt.value.trim() });
  url.value = "";
  alt.value = "";
}
async function upload(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  error.value = "";
  uploading.value = true;
  emit("busy", true);
  try {
    if (props.modelValue.length >= 12) throw new Error(t("staff.mediaLimit"));
    const body = new FormData();
    body.append("file", file);
    body.append("resortId", props.resortId);
    append(await request("POST", "/media", body));
  } catch (e) {
    error.value = e.message;
  } finally {
    uploading.value = false;
    emit("busy", false);
    event.target.value = "";
  }
}
</script>
<template>
  <section class="media-editor" :aria-label="t('staff.photosVideos')">
    <h3>{{ t("staff.photosVideos") }}</h3>
    <p class="field-help">
      {{ t("staff.mediaCoverHint") }}
    </p>
    <div
      v-for="(item, index) in modelValue"
      :key="index"
      class="media-editor-row"
    >
      <img
        v-if="item.kind === 'image'"
        :src="item.url"
        :alt="item.alt || t('staff.photo')"
        loading="lazy"
      />
      <video v-else :src="item.url" controls preload="metadata"></video>
      <label
        >{{ t("staff.mediaDescription", { number: index + 1 })
        }}<input
          :value="item.alt"
          maxlength="200"
          @input="
            emit(
              'update:modelValue',
              modelValue.map((entry, i) =>
                i === index ? { ...entry, alt: $event.target.value } : entry,
              ),
            )
          "
      /></label>
      <button
        type="button"
        class="text-button danger"
        :disabled="uploading"
        @click="
          emit(
            'update:modelValue',
            modelValue.filter((_, i) => i !== index),
          )
        "
      >
        {{ t("staff.deleteMedia", { number: index + 1 }) }}
      </button>
    </div>
    <label v-if="!isDemo && resortId"
      >{{ t("staff.uploadMedia")
      }}<input
        type="file"
        accept="image/jpeg,image/png,image/webp,video/mp4,video/webm"
        :disabled="uploading"
        @change="upload"
    /></label>
    <p v-if="!resortId && !isDemo" class="field-help">
      {{ t("staff.saveBeforeUpload") }}
    </p>
    <div class="form-grid">
      <label
        >{{ t("staff.type")
        }}<select v-model="kind">
          <option value="image">{{ t("staff.photograph") }}</option>
          <option value="video">{{ t("staff.video") }}</option>
        </select></label
      >
      <label
        >{{ t("staff.link") }}<input v-model="url" placeholder="https://…"
      /></label>
      <label
        >{{ t("staff.description") }}<input v-model="alt" maxlength="200"
      /></label>
      <button
        type="button"
        class="secondary"
        :disabled="uploading || !url.trim()"
        @click="addUrl"
      >
        {{ t("staff.addByLink") }}
      </button>
    </div>
    <p v-if="uploading" role="status">{{ t("staff.uploadingFile") }}</p>
    <p v-if="error" role="alert" class="form-error">{{ error }}</p>
    <p v-if="isDemo" class="field-help">
      {{ t("staff.demoMediaHint") }}
    </p>
  </section>
</template>
