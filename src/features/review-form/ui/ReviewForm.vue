<script setup>
import { useI18n } from "vue-i18n";
const { t } = useI18n();
import { ref } from "vue";
import { Modal } from "@/shared/ui";
import { request } from "@/shared/api";
const props = defineProps({ booking: { type: Object, required: true } });
const emit = defineEmits(["close", "saved"]);
const rating = ref(5),
  text = ref(""),
  photos = ref([]),
  busy = ref(false),
  uploading = ref(false),
  error = ref("");
async function upload(event) {
  const files = [...event.target.files];
  event.target.value = "";
  error.value = "";
  if (photos.value.length + files.length > 5) {
    error.value = t("public.aReviewCanIncludeUpTo5Photos");
    return;
  }
  if (
    files.some(
      (f) =>
        !["image/jpeg", "image/png", "image/webp"].includes(f.type) ||
        f.size > 8 * 1024 * 1024,
    )
  ) {
    error.value = t("public.chooseAJpgPngOrWebpImageUpTo8Mb");
    return;
  }
  uploading.value = true;
  try {
    for (const file of files) {
      const body = new FormData();
      body.append("file", file);
      body.append("bookingId", props.booking.id);
      const uploaded = await request("POST", "/media", body);
      photos.value.push(uploaded.url);
    }
  } catch (e) {
    error.value = e.message;
  } finally {
    uploading.value = false;
  }
}
async function save() {
  busy.value = true;
  error.value = "";
  try {
    const result = await request("POST", "/reviews", {
      bookingId: props.booking.id,
      rating: rating.value,
      text: text.value.trim(),
      photos: photos.value,
    });
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
    :title="t('public.reviewOf', [booking.resortName])"
    :busy="busy || uploading"
    @close="emit('close')"
    ><form class="editor-form" @submit.prevent="save">
      <p class="field-help">
        {{ t("public.yourStayHasEndedYourReviewWillAppearOnTheResortPage") }}
      </p>
      <fieldset class="review-rating-input">
        <legend>{{ t("public.yourRating") }}</legend>
        <label
          v-for="value in 5"
          :key="value"
          :class="{ selected: rating === value }"
          ><input
            v-model="rating"
            type="radio"
            name="review-rating"
            :value="value"
            required
          /><span>{{ value }} ★</span></label
        >
      </fieldset>
      <label
        >{{ t("public.yourExperience")
        }}<textarea
          v-model="text"
          minlength="10"
          maxlength="3000"
          rows="5"
          required
          :placeholder="t('public.tellUsAboutTheRoomMealsAndYourStay')"
        ></textarea></label
      ><label
        >{{ t("public.photosUpTo5Files")
        }}<input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          :disabled="uploading || busy || photos.length >= 5"
          @change="upload"
      /></label>
      <p class="field-help">
        {{ t("public.jpgPngOrWebpUpTo8MbPerPhotoDoNot") }}
      </p>
      <p v-if="uploading" role="status">{{ t("public.uploadingPhotos") }}</p>
      <div v-if="photos.length" class="review-upload-previews">
        <div v-for="(photo, index) in photos" :key="photo">
          <img :src="photo" :alt="t('public.selectedPhoto')" /><button
            type="button"
            :disabled="busy || uploading"
            :aria-label="t('public.removePhoto', [index + 1])"
            @click="photos.splice(index, 1)"
          >
            ×
          </button>
        </div>
      </div>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <div class="form-actions">
        <button
          class="secondary"
          type="button"
          :disabled="busy || uploading"
          @click="emit('close')"
        >
          {{ t("public.cancel") }}</button
        ><button class="primary" :disabled="busy || uploading">
          {{ busy ? t("public.sending") : t("public.submitReview") }}
        </button>
      </div>
    </form></Modal
  >
</template>
