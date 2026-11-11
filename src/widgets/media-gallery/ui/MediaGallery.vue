<script setup>
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Modal } from "@/shared/ui";
const { t } = useI18n();
const props = defineProps({
  media: { type: Array, default: () => [] },
  title: String,
  fallback: { type: String, default: "/assets/resort.jpg" },
});
const index = ref(0),
  failed = ref(false),
  expanded = ref(false),
  video = ref(null);
const items = computed(() =>
  props.media.filter((m) => ["image", "video"].includes(m?.kind) && m.url),
);
const current = computed(() => items.value[index.value]);
let start = null;
function move(step) {
  if (items.value.length)
    index.value =
      (index.value + step + items.value.length) % items.value.length;
}
function swipe(event) {
  if (!start) return;
  const dx = event.changedTouches[0].clientX - start.x,
    dy = event.changedTouches[0].clientY - start.y;
  if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.5)
    move(dx < 0 ? 1 : -1);
  start = null;
}
function keyboard(event) {
  if (event.target.tagName === "VIDEO") return;
  if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
    event.preventDefault();
    move(event.key === "ArrowLeft" ? -1 : 1);
  }
}
watch(
  () => props.media,
  () => {
    index.value = 0;
    failed.value = false;
  },
  { deep: true },
);
watch(index, () => {
  failed.value = false;
});
watch(expanded, () => video.value?.pause());
</script>
<template>
  <section
    class="media-gallery"
    :aria-label="t('public.photosAndVideos', [title])"
    @keydown="keyboard"
  >
    <div
      class="media-main"
      tabindex="0"
      @touchstart.passive="
        start = { x: $event.touches[0].clientX, y: $event.touches[0].clientY }
      "
      @touchend.passive="swipe"
    >
      <video
        v-if="current?.kind === 'video' && !failed"
        ref="video"
        :key="current.url"
        :src="current.url"
        controls
        preload="metadata"
        playsinline
        :aria-label="current.alt || t('public.video', [title])"
        @error="failed = true"
      />
      <img
        v-else
        :src="failed ? fallback : current?.url || fallback"
        :alt="current?.alt || title || ''"
        @error="failed = true"
        @click="expanded = true"
      />
      <span class="media-caption" role="status">
        {{ failed ? t("public.mediaCouldNotLoadAnIllustrativeImageIsShown") : `${index + 1} / ${items.length || 1}` }}
      </span>
      <button
        v-if="items.length > 1"
        type="button"
        class="gallery-arrow previous"
        :aria-label="t('common.gallery.previous')"
        @click="move(-1)"
      >
        ‹
      </button>
      <button
        v-if="items.length > 1"
        type="button"
        class="gallery-arrow next"
        :aria-label="t('common.gallery.next')"
        @click="move(1)"
      >
        ›
      </button>
      <button type="button" class="gallery-expand" @click="expanded = true">
        ⛶ {{ t("common.gallery.open") }}
      </button>
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
        type="button"
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
    <Modal
      v-if="expanded"
      :title="title || t('common.gallery.open')"
      wide
      @close="expanded = false"
    >
      <div
        class="gallery-viewer"
        tabindex="0"
        @keydown="keyboard"
        @touchstart.passive="
          start = { x: $event.touches[0].clientX, y: $event.touches[0].clientY }
        "
        @touchend.passive="swipe"
      >
        <video
          v-if="current?.kind === 'video' && !failed"
          :key="current.url"
          :src="current.url"
          controls
          playsinline
          preload="metadata"
          :aria-label="current.alt || title"
          @error="failed = true"
        />
        <img
          v-else
          :src="failed ? fallback : current?.url || fallback"
          :alt="current?.alt || title || ''"
          @error="failed = true"
        />
      </div>
      <div class="gallery-controls">
        <button
          type="button"
          class="secondary"
          :disabled="items.length < 2"
          @click="move(-1)"
        >
          {{ t("common.gallery.previous") }}</button
        ><span role="status"
          >{{ items.length ? index + 1 : 1 }} / {{ items.length || 1 }}</span
        ><button
          type="button"
          class="secondary"
          :disabled="items.length < 2"
          @click="move(1)"
        >
          {{ t("common.gallery.next") }}
        </button>
      </div>
    </Modal>
  </section>
</template>
<style scoped>
.media-gallery {
  min-width: 0;
}
.media-main {
  touch-action: pan-y;
}
.media-main > img {
  cursor: zoom-in;
}
.gallery-arrow,
.gallery-expand {
  position: absolute;
  background: #132e28e8;
  color: white;
  border: 1px solid #ffffff99;
  border-radius: 10px;
  min-width: 44px;
  min-height: 44px;
  cursor: pointer;
}
.gallery-arrow {
  top: 45%;
  font-size: 30px;
}
.previous {
  left: 12px;
}
.next {
  right: 12px;
}
.gallery-expand {
  right: 12px;
  top: 12px;
  padding: 8px 12px;
}
.media-thumbnails button {
  min-height: 60px;
}
.gallery-viewer {
  background: #14261f;
  display: grid;
  place-items: center;
  min-height: 220px;
  touch-action: pan-y;
  border-radius: 12px;
  overflow: hidden;
}
.gallery-viewer img,
.gallery-viewer video {
  max-width: 100%;
  width: 100%;
  max-height: 65vh;
  object-fit: contain;
}
.gallery-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
}
.gallery-controls button {
  min-height: 44px;
}
.gallery-controls span {
  white-space: nowrap;
}
</style>
