<script setup>
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
  markers,
  observer,
  failed = false;
function redraw() {
  if (!map) return;
  markers.clearLayers();
  const points = props.editable
    ? [
        {
          id: "location",
          name: "Место санатория",
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
    node.textContent = props.editable ? "● Санаторий" : p.label;
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
        props.editable ? "Место санатория" : `${p.name}, ${p.label}`,
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
      { padding: [65, 65], maxZoom: 16 },
    );
}
onMounted(() => {
  map = L.map(element.value, { zoomControl: false }).setView(
    [props.lat, props.lng],
    16,
  );
  L.control.zoom({ position: "bottomright" }).addTo(map);
  const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  });
  tiles.on("tileerror", () => {
    failed = true;
    error.value =
      "Не все участки карты загрузились. Можно продолжить через список или координаты.";
    loading.value = false;
  });
  tiles.on("load", () => {
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
  observer = new ResizeObserver(() => map.invalidateSize());
  observer.observe(element.value);
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
  map?.remove();
});
defineExpose({ reset });
</script>
<template>
  <div class="geo-wrap">
    <div
      ref="element"
      class="geo-map"
      :aria-label="
        editable ? 'Выбрать положение санатория на карте' : 'Карта санаториев'
      "
    ></div>
    <div v-if="error || loading" class="geo-notice" role="status">
      {{ error || "Загружаем карту…" }}
    </div>
    <button
      v-if="!editable"
      class="map-reset"
      type="button"
      aria-label="Показать все санатории"
      @click="reset"
    >
      ◎
    </button>
    <div v-else class="geo-tip">Нажмите на карту, чтобы поставить метку</div>
  </div>
</template>
