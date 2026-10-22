<script setup>
import { useI18n } from "vue-i18n";
const { t, locale } = useI18n();

import { ref, watch, onMounted, onBeforeUnmount } from "vue";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
const props = defineProps({
  points: { type: Array, default: () => [] },
  selected: String,
  editable: Boolean,
  lat: { type: Number, default: 41.385 },
  lng: { type: Number, default: 69.061 },
});
const emit = defineEmits(["select", "location"]);
const element = ref();
const error = ref("");
const loading = ref(true);
let map,
  zoom,
  markers,
  tiles,
  observer,
  failed = false;
function redraw() {
  if (!map) return;
  markers.clearLayers();
  const points = props.editable
    ? [
        {
          id: "location",
          name: t("staff.resortLocation"),
          lat: props.lat,
          lng: props.lng,
        },
      ]
    : props.points;
  for (const p of points) {
    if (
      !Number.isFinite(p.lat) ||
      !Number.isFinite(p.lng) ||
      Math.abs(p.lat) > 90 ||
      Math.abs(p.lng) > 180
    )
      continue;
    const node = document.createElement("span");
    node.className = `price-marker ${p.id === props.selected ? "selected" : ""}`;
    node.textContent = props.editable ? t("staff.resortMarker") : p.label;
    const marker = L.marker([p.lat, p.lng], {
      icon: L.divIcon({
        className: "price-marker-wrap",
        html: node,
        iconSize: [120, 38],
        iconAnchor: [60, 38],
      }),
      title: p.name,
      keyboard: true,
      riseOnHover: true,
    }).addTo(markers);
    const tooltip = document.createElement("span");
    tooltip.textContent = p.name;
    marker.bindTooltip(tooltip);
    marker.on("click", () => emit("select", p.id));
    marker.getElement()?.setAttribute("role", "button");
    marker
      .getElement()
      ?.setAttribute(
        "aria-label",
        props.editable ? t("staff.resortLocation") : `${p.name}, ${p.label}`,
      );
  }
}
function reset() {
  const points = props.points.filter(
    (p) => Number.isFinite(p.lat) && Number.isFinite(p.lng),
  );
  if (map && points.length)
    map.fitBounds(
      points.map((p) => [p.lat, p.lng]),
      { padding: [65, 65], maxZoom: 16, animate: false },
    );
}
onMounted(() => {
  // Leaflet 1.9 leaves its CSS zoom timeout alive after remove().
  map = L.map(element.value, {
    zoomControl: false,
    zoomAnimation: false,
    markerZoomAnimation: false,
  }).setView([props.lat, props.lng], 16);
  updateZoom();
  tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  });
  tiles.on("tileerror", () => {
    if (!map) return;
    failed = true;
    error.value = t("staff.mapPartialError");
    loading.value = false;
  });
  tiles.on("load", () => {
    if (!map) return;
    loading.value = false;
    if (!failed) error.value = "";
  });
  tiles.addTo(map);
  markers = L.layerGroup().addTo(map);
  redraw();
  if (!props.editable) reset();
  if (props.editable)
    map.on("click", (e) =>
      emit("location", {
        lat: Number(e.latlng.lat.toFixed(6)),
        lng: Number(e.latlng.lng.toFixed(6)),
      }),
    );
  observer = new ResizeObserver(() => map?.invalidateSize({ animate: false }));
  observer.observe(element.value);
});
function updateZoom() {
  if (!map) return;
  zoom?.remove();
  zoom = L.control
    .zoom({
      position: "bottomright",
      zoomInTitle: t("staff.zoomIn"),
      zoomOutTitle: t("staff.zoomOut"),
    })
    .addTo(map);
}
watch(locale, () => {
  redraw();
  updateZoom();
  if (failed) error.value = t("staff.mapPartialError");
});
watch(() => [props.points, props.selected, props.lat, props.lng], redraw, {
  deep: true,
});
watch(
  () => props.selected,
  (id) => {
    const p = props.points.find((p) => p.id === id);
    if (p && map)
      map.panTo([p.lat, p.lng], {
        animate: !matchMedia("(prefers-reduced-motion: reduce)").matches,
      });
  },
);
onBeforeUnmount(() => {
  observer?.disconnect();
  const currentMap = map;
  map = null;
  tiles?.off();
  currentMap?.stop();
  currentMap?.remove();
  markers = null;
  zoom = null;
  tiles = null;
  observer = null;
});
defineExpose({ reset });
</script>
<template>
  <div class="geo-wrap">
    <div
      ref="element"
      class="geo-map"
      :aria-label="
        editable ? t('staff.chooseMapLocation') : t('staff.resortMap')
      "
    ></div>
    <div v-if="error || loading" class="geo-notice" role="status">
      {{ error || t("staff.loadingMap") }}
    </div>
    <button
      v-if="!editable"
      class="map-reset"
      type="button"
      :aria-label="t('staff.showAllResorts')"
      @click="reset"
    >
      ◎
    </button>
    <div v-else class="geo-tip">{{ t("staff.placeMapMarker") }}</div>
  </div>
</template>
