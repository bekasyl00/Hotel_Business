<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { requestFile } from "../api";
import { apiBase } from "../config";

const props = defineProps({ name: String, photo: String });
const root = ref(null);
const visible = ref(false);
const image = ref("");
const initials = computed(() => (props.name || "").trim().split(/\s+/u)
  .filter(Boolean).slice(0, 2).map((word) => Array.from(word)[0]).join("").toLocaleUpperCase() || "•");
let observer;
onMounted(() => {
  if (!("IntersectionObserver" in window)) {
    visible.value = true;
    return;
  }
  observer = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) {
      visible.value = true;
      observer.disconnect();
    }
  }, { rootMargin: "100px" });
  observer.observe(root.value);
});
onBeforeUnmount(() => observer?.disconnect());
watch([visible, () => props.photo], async ([shown, photo], _, onCleanup) => {
  image.value = "";
  if (!shown || !photo) return;
  if (!photo.startsWith("/api/media/files/")) {
    image.value = photo;
    return;
  }
  let current = true;
  let objectUrl;
  onCleanup(() => {
    current = false;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
  });
  try {
    const file = await requestFile(photo.slice(4), apiBase, "image/");
    if (current) image.value = objectUrl = URL.createObjectURL(file);
  } catch { /* Missing or inaccessible photos keep the initials. */ }
});
</script>
<template>
  <div ref="root" class="guest-identity">
    <span class="guest-avatar" aria-hidden="true">
      <img v-if="image" :src="image" alt="" @error="image = ''" />
      <template v-else>{{ initials }}</template>
    </span>
    <div class="guest-caption"><slot /></div>
  </div>
</template>
<style scoped>
.guest-identity { display: flex; align-items: center; gap: .65rem; min-width: 0; }
.guest-avatar { display: grid; place-items: center; flex: none; width: var(--avatar-size, 36px); aspect-ratio: 1; overflow: hidden; border-radius: 50%; background: #e8eee8; color: #355143; font-size: .8rem; font-weight: 600; }
.guest-avatar img { display: block; width: 100%; height: 100%; object-fit: cover; }
.guest-caption { min-width: 0; }
</style>
