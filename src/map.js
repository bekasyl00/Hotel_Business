import { money } from "./domain.js";
export function createMap(onSelect) {
  const status = document.querySelector("#map-status");
  if (!window.L) {
    status.textContent = "Карта недоступна. Выберите санаторий в списке.";
    return { update() {}, focus() {}, reset() {} };
  }
  const map = L.map("map", {
    zoomControl: false,
    scrollWheelZoom: true,
  }).setView([41.385, 69.061], 16);
  L.control.zoom({ position: "bottomright" }).addTo(map);
  const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  let errors = 0;
  tiles.on("loading", () => {
    errors = 0;
  });
  tiles.on("tileerror", () => {
    errors++;
    status.hidden = false;
    status.textContent =
      "Не все участки карты загрузились. Список и выбор номеров доступны.";
  });
  tiles.on("load", () => {
    if (!errors) status.hidden = true;
  });
  const markers = L.layerGroup().addTo(map);
  let current = [];
  return {
    update(items, selected) {
      current = items;
      markers.clearLayers();
      items.forEach((resort) => {
        const icon = L.divIcon({
          className: "price-marker-wrap",
          html: `<span class="price-marker ${selected === resort.id ? "selected" : ""}"><span class="marker-leaf">✦</span> ${resort.displayPrice ? money(resort.displayPrice) : "Нет мест"}</span>`,
          iconSize: [114, 38],
          iconAnchor: [57, 38],
        });
        const marker = L.marker([resort.lat, resort.lng], {
          icon,
          title: resort.name,
          keyboard: true,
        }).addTo(markers);
        marker.bindTooltip(resort.name, { direction: "top", offset: [0, -36] });
        marker.on("click", () => onSelect(resort.id));
        const el = marker.getElement();
        if (el) {
          el.setAttribute("role", "button");
          el.setAttribute(
            "aria-label",
            `${resort.name}, ${resort.displayPrice ? "от " + money(resort.displayPrice) : "нет мест"}`,
          );
        }
      });
    },
    focus(resort) {
      map.flyTo([resort.lat, resort.lng], 16, {
        duration: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? 0
          : 0.5,
      });
    },
    reset() {
      if (current.length)
        map.fitBounds(
          current.map((r) => [r.lat, r.lng]),
          { padding: [70, 70], maxZoom: 16 },
        );
    },
  };
}
