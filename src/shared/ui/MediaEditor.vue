<script setup>
import { useI18n } from "vue-i18n";
import { ref, nextTick } from "vue";
import { request, ApiError, uploadErrorCode } from "../api/index.js";
import { isDemo } from "../config/index.js";
const { t } = useI18n();
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  resortId: String,
});
const emit = defineEmits(["update:modelValue", "busy"]);
const error = ref(""),
  uploading = ref(false),
  pendingFiles = ref([]);
function append(item) {
  emit("update:modelValue", [...props.modelValue, item]);
}
async function upload(event) {
  const files = [...(event.target.files || [])];
  event.target.value = "";
  if (!files.length) return;
  pendingFiles.value = files;
  await uploadPending();
}
async function uploadPending() {
  error.value = "";
  uploading.value = true;
  emit("busy", true);
  try {
    if (props.modelValue.length + pendingFiles.value.length > 12)
      throw new Error(t("staff.mediaLimit"));
    for (const file of pendingFiles.value) {
      const code = uploadErrorCode(file, { allowVideo: true });
      if (code) throw new ApiError(null, 422, {}, code);
    }
    while (pendingFiles.value.length) {
      const body = new FormData();
      body.append("file", pendingFiles.value[0]);
      body.append("resortId", props.resortId);
      append(await request("POST", "/media", body));
      pendingFiles.value.shift();
      await nextTick();
    }
  } catch (e) {
    error.value = e.message;
  } finally {
    uploading.value = false;
    emit("busy", false);
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
      <video
        v-else
        :src="item.url"
        controls
        playsinline
        preload="metadata"
        :aria-label="item.alt || t('staff.video')"
      ></video>
      <label
        >{{ t("staff.mediaDescription", { number: index + 1 })
        }}<input
          :value="item.alt"
          :disabled="uploading"
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
    <label v-if="resortId"
      >{{ t("staff.uploadMedia")
      }}<input
        type="file"
        accept="image/jpeg,image/png,image/webp,video/mp4,video/webm"
        multiple
        :disabled="uploading || modelValue.length >= 12"
        @change="upload"
    /></label>
    <p v-if="!resortId" class="field-help">
      {{ t("staff.saveBeforeUpload") }}
    </p>
    <p class="field-help">{{ t("common.media.catalogHint") }}</p>
    <p v-if="uploading" role="status">{{ t("staff.uploadingFile") }}</p>
    <p v-if="error" role="alert" class="form-error">{{ error }}</p>
    <button
      v-if="error && pendingFiles.length"
      type="button"
      class="secondary"
      :disabled="uploading"
      @click="uploadPending"
    >
      {{ t("auth.retry") }}
    </button>
    <p v-if="isDemo" class="field-help">
      {{ t("common.media.demoHint") }}
    </p>
  </section>
</template>
