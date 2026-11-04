<script setup>
import { useI18n } from "vue-i18n";
const { t } = useI18n();
import { computed, ref, watch } from "vue";
const props = defineProps({
  media: { type: Array, default: () => [] },
  title: String,
  fallback: { type: String, default: "/assets/resort.jpg" },
});
const index = ref(0),
  failed = ref(false);
const items = computed(() =>
  props.media.filter((m) => ["image", "video"].includes(m.kind) && m.url),
);
const current = computed(() => items.value[index.value]);
watch(
  () => props.media,
  () => {
    index.value = 0;
    failed.value = false;
  },
);
watch(index, () => {
  failed.value = false;
});
</script>
<template>
  <section
    class="media-gallery"
    :aria-label="t('public.photosAndVideos', [title])"
  >
    <div class="media-main">
      <video
        v-if="current?.kind === 'video' && !failed"
        :key="current.url"
        :src="current.url"
        controls
        preload="metadata"
        playsinline
        :aria-label="current.alt || t('public.video', [title])"
        @error="failed = true"
      ></video
      ><img
        v-else
        :src="failed ? fallback : current?.url || fallback"
        :alt="
          failed || !current
            ? t('public.illustration', [title])
            : current.alt || title
        "
        @error="failed = true"
      /><span v-if="!current" class="media-caption">{{
        t("public.illustrativePhoto")
      }}</span
      ><span v-else-if="failed" class="media-caption" role="status">{{
        t("public.mediaCouldNotLoadAnIllustrativeImageIsShown")
      }}</span
      ><span v-else class="media-caption"
        >{{
          current.kind === "video"
            ? t("public.videoInMediaGallery")
            : t("public.photo")
        }}
        {{ index + 1 }} / {{ items.length }}</span
      >
    </div>
    <div
      v-if="items.length > 1"
      class="media-thumbnails"
      role="group"
      :aria-label="t('public.chooseAPhotoOrVideo')"
    >
      <button
        v-for="(item, i) in items"
        :key="item.url + i"
        :class="{ selected: i === index }"
        :aria-label="`${item.kind === 'video' ? t('public.videoInMediaGallery') : t('public.photo')} ${i + 1}`"
        :aria-pressed="i === index"
        @click="index = i"
      >
        <span v-if="item.kind === 'video'" class="video-thumbnail"
          >▷<small>{{ t("public.videoInMediaGallery") }}</small></span
        ><img v-else :src="item.url" alt="" loading="lazy" />
      </button>
    </div>
  </section>
</template>
