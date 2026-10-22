import { resorts, tariffs } from "./data.js";
import {
  money,
  dateAfter,
  validateSearch,
  availableUnits,
  quote,
  reserve,
} from "./domain.js";
import { readBookings, writeBookings, storageKey } from "./storage.js";
import { createMap } from "./map.js";

const $ = (selector) => document.querySelector(selector);
const escape = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
let search = { start: dateAfter(7), end: dateAfter(10), guests: 2 };
let selectedId = null;
let roomId = null;
let tariffId = "stay";
let pending = null;
let returnFocus = null;
// Seeded occupancy is illustrative and separate from the user's local bookings.
const blocks = resorts.flatMap((resort, index) =>
  resort.rooms.flatMap((room) =>
    (index === 5 ? room.units : [room.units[0]]).map((unit) => ({
      roomId: room.id,
      unit,
      start: dateAfter(5),
      end: dateAfter(12),
      status: "confirmed",
    })),
  ),
);
let bookings = [];
let storageError = "";
function syncStorage() {
  try {
    bookings = readBookings();
    storageError = "";
  } catch (error) {
    storageError = error.message || "Хранилище браузера недоступно.";
    toast("Бронирования недоступны: " + storageError);
  }
}
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    $("#toast").hidden = true;
  }, 6500);
}
const allReservations = () => [...blocks, ...bookings];
const selectedResort = () => resorts.find((r) => r.id === selectedId);
const roomFilter = (room) =>
  $("#room-class").value === "all" || room.category === $("#room-class").value;
function freeRooms(resort) {
  return resort.rooms.filter(
    (r) => roomFilter(r) && availableUnits(r, search, allReservations()).length,
  );
}
function filteredResorts() {
  const query = $("#query").value.trim().toLocaleLowerCase();
  let list = resorts
    .filter(
      (r) =>
        !query ||
        `${r.name} Сарыагаш Коктерек`.toLocaleLowerCase().includes(query),
    )
    .map((r) => {
      const rooms = freeRooms(r);
      return {
        ...r,
        displayPrice: rooms.length
          ? Math.min(...rooms.map((room) => room.price))
          : 0,
        freeCount: rooms.reduce(
          (sum, room) =>
            sum + availableUnits(room, search, allReservations()).length,
          0,
        ),
      };
    });
  if ($("#available-only").checked) list = list.filter((r) => r.freeCount > 0);
  if ($("#sort").value === "price")
    list.sort(
      (a, b) => (a.displayPrice || Infinity) - (b.displayPrice || Infinity),
    );
  if ($("#sort").value === "rating") list.sort((a, b) => b.rating - a.rating);
  return list;
}
const map = createMap(selectResort);
$("#check-in").value = search.start;
$("#check-in").min = dateAfter();
$("#check-out").value = search.end;
$("#check-out").min = dateAfter(1);
syncStorage();

function renderList() {
  const list = filteredResorts();
  $("#results-summary").textContent =
    `${list.length} санаториев · ${search.guests} гостя · найдите свой ритм`;
  $("#resort-list").innerHTML = list.length
    ? list
        .map(
          (r, i) => `
    <article class="resort-card ${selectedId === r.id ? "active" : ""}">
      <button class="resort-card-button" data-resort="${r.id}" aria-label="Выбрать санаторий ${r.name}">
        <div class="resort-photo photo-${i % 3}"><img src="${r.image}" alt="Иллюстрация курортного отеля" loading="${i > 1 ? "lazy" : "eager"}">${r.badge ? `<span class="photo-badge">${r.badge}</span>` : ""}</div>
        <div class="resort-info"><div class="card-title-row"><h2>${r.name}</h2><span class="rating">★ ${r.rating.toFixed(1)}</span></div><p class="resort-location">Сарыагаш · курортная зона</p><p class="resort-subtitle">${r.subtitle}</p><div class="amenity-line"><span>♧ ${r.feature}</span><span>Wi-Fi</span></div><div class="card-bottom"><span class="availability ${r.freeCount ? "" : "sold-out"}">${r.freeCount ? `${r.freeCount} номера доступны` : "Нет мест на эти даты"}</span><span class="card-price">${r.displayPrice ? `<small>от </small>${money(r.displayPrice)}<small> / ночь</small>` : "Другие даты →"}</span></div></div>
      </button>
    </article>`,
        )
        .join("")
    : '<div class="empty-state"><span>⌕</span><h2>Пока ничего не нашлось</h2><p>Попробуйте другие даты, категорию или название.</p><button class="secondary" id="reset-filters">Сбросить фильтры</button></div>';
  map.update(list, selectedId);
  $("#booking-count").textContent = bookings.filter(
    (b) => b.status === "confirmed",
  ).length;
}
function selectResort(id) {
  selectedId = id;
  roomId = null;
  tariffId = "stay";
  renderList();
  renderDetails();
  map.focus(selectedResort());
  $("#details").scrollTop = 0;
  $("#details-close").focus({ preventScroll: true });
}
function closeDetails() {
  selectedId = null;
  roomId = null;
  $("#details").hidden = true;
  renderList();
  $("#resort-list button")?.focus({ preventScroll: true });
}
function renderDetails() {
  const resort = selectedResort();
  if (!resort) {
    $("#details").hidden = true;
    return;
  }
  const rooms = resort.rooms.filter(roomFilter);
  const available = freeRooms(resort);
  if (!available.some((r) => r.id === roomId))
    roomId = available[0]?.id ?? null;
  const room = resort.rooms.find((r) => r.id === roomId);
  const tariff = tariffs.find((t) => t.id === tariffId);
  $("#details").hidden = false;
  $("#details").innerHTML = `
    <div class="detail-nav"><span>${resort.name}</span><button id="details-close" class="icon-button" aria-label="Закрыть санаторий">×</button></div>
    <div class="detail-cover"><img src="${resort.image}" alt="Иллюстративное фото курорта"><span class="photo-badge">САРЫАГАШ</span></div>
    <div class="detail-body"><div class="card-title-row"><h2>${resort.name}</h2><span class="rating">★ ${resort.rating}</span></div><p class="muted">${resort.subtitle}</p><p class="detail-description">${resort.description}</p>
    <div class="step-title"><span>01</span><h3>Выберите номер</h3></div><p class="small muted">${formatDate(search.start)} — ${formatDate(search.end)} · ${search.guests} гостя</p>
    <div class="room-options">${rooms
      .map((r) => {
        const count = availableUnits(r, search, allReservations()).length;
        return `
      <label class="room-option ${roomId === r.id ? "chosen" : ""} ${count ? "" : "unavailable"}"><input type="radio" name="room" value="${r.id}" ${roomId === r.id ? "checked" : ""} ${!count ? "disabled" : ""}><img src="${r.image}" alt="Иллюстрация номера"><span class="room-copy"><strong>${r.title} <span class="small">${r.area} м²</span></strong><span class="small muted">До ${r.capacity} гостей · ${r.beds}</span><span class="small muted">${r.amenities.join(" · ")}</span><span class="room-bottom"><strong>${money(r.price)}<small> / ночь</small></strong><span class="small ${count ? "green" : ""}">${count ? `${count} свободно` : search.guests > r.capacity ? "Мало мест для гостей" : "Занято"}</span></span></span></label>`;
      })
      .join("")}</div>
    ${room ? `<div class="step-title"><span>02</span><h3>Ваш формат отдыха</h3></div><div class="tariff-options">${tariffs.map((t) => `<label class="tariff-option ${tariffId === t.id ? "chosen" : ""}"><input type="radio" name="tariff" value="${t.id}" ${tariffId === t.id ? "checked" : ""}><span><strong>${t.name}</strong><span class="small muted">${t.description}</span><span class="small">${t.features.join(" · ")}</span></span><b>${t.supplement ? "+" + money(t.supplement) : "Включено"}<small>${t.supplement ? "за гостя / ночь" : "в цену номера"}</small></b></label>`).join("")}</div><p class="small muted">Демо-условия: отмена без штрафа. Оздоровительная программа иллюстративная; состав услуг уточняется при реальном подключении санатория.</p>` : '<div class="empty-state"><h3>На эти даты нет подходящих номеров</h3><p>Измените даты, число гостей или категорию в поиске.</p></div>'}
    </div>${room ? `<div class="booking-footer"><div><span class="small muted">${quote(room, tariff, search).nights} ночи · ${search.guests} гостя · ${tariff.name}</span><strong>${money(quote(room, tariff, search).total)}</strong></div><button id="start-booking" class="primary">Выбрать <span aria-hidden="true">→</span></button></div>` : ""}`;
}
function formatDate(value) {
  return new Intl.DateTimeFormat("ru", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(value));
}
function openDialog(id) {
  returnFocus = document.activeElement;
  $(id).showModal();
}
function closeDialog(id) {
  $(id).close();
  if (returnFocus?.isConnected) returnFocus.focus();
}
function openBooking() {
  syncStorage();
  if (storageError) return;
  const resort = selectedResort();
  const room = resort.rooms.find((r) => r.id === roomId);
  const tariff = tariffs.find((t) => t.id === tariffId);
  if (!room || !availableUnits(room, search, allReservations()).length) {
    renderDetails();
    toast("Наличие изменилось. Выберите свободный номер.");
    return;
  }
  pending = { resort, room, tariff, search: { ...search } };
  const price = quote(room, tariff, search);
  $("#booking-content").innerHTML =
    `<div class="dialog-top"><div><span class="eyebrow">ВАШ ОТДЫХ</span><h2 id="booking-title">Всё готово к бронированию</h2></div><button class="icon-button" data-close="booking-dialog" aria-label="Закрыть">×</button></div><div class="booking-preview"><img src="${room.image}" alt="Иллюстрация номера"><div><h3>${resort.name}</h3><p>${room.title} · ${room.area} м²</p><span class="small muted">${tariff.name}</span></div></div><dl class="summary"><div><dt>Даты</dt><dd>${formatDate(search.start)} — ${formatDate(search.end)}</dd></div><div><dt>Гости</dt><dd>${search.guests} взрослых</dd></div><div><dt>Номер · ${price.nights} ночи</dt><dd>${money(room.price * price.nights)}</dd></div><div><dt>Дополнение к тарифу</dt><dd>${money(tariff.supplement * search.guests * price.nights)}</dd></div><div class="summary-total"><dt>Итого</dt><dd>${money(price.total)}</dd></div></dl><div class="demo-notice">Это демонстрация. Оплата не списывается, настоящий номер не резервируется. Бронь сохраняется на этом устройстве.</div><form id="confirm-form"><label class="consent"><input type="checkbox" required> Я понимаю, что создаю демонстрационную бронь</label><p id="booking-error" class="error" role="alert" hidden></p><button class="primary full-width" type="submit">Создать демо-бронь</button></form>`;
  openDialog("#booking-dialog");
}
function confirmBooking(event) {
  event.preventDefault();
  try {
    // Re-read immediately before allocation, so another tab's changes are considered.
    bookings = readBookings();
    const reservation = reserve({
      ...pending,
      reservations: allReservations(),
    });
    writeBookings([...bookings, reservation]);
    bookings.push(reservation);
    $("#booking-content").innerHTML =
      `<div class="success-view"><div class="success-icon">✓</div><span class="eyebrow">МОЖНО ВЫДОХНУТЬ</span><h2 id="booking-title">Демо-бронь создана</h2><p>${escape(reservation.resortName)} · ${reservation.roomName}</p><p class="muted">${formatDate(reservation.start)} — ${formatDate(reservation.end)} · ${money(reservation.total)}</p><code>№ ${reservation.id.slice(0, 8).toUpperCase()}</code><p class="small muted">Она доступна в «Моих бронированиях».<br>Реальное бронирование не выполнялось.</p><button class="primary full-width" data-close="booking-dialog">Продолжить поиск</button></div>`;
    pending = null;
    renderList();
    renderDetails();
    $("#booking-dialog button").focus();
  } catch (error) {
    $("#booking-error").hidden = false;
    $("#booking-error").textContent =
      error.message ||
      "Не удалось сохранить бронь. Проверьте доступ к хранилищу браузера.";
  }
}
function renderBookings() {
  $("#my-bookings").innerHTML = storageError
    ? `<p class="error">${escape(storageError)}</p>`
    : bookings.length
      ? [...bookings]
          .reverse()
          .map(
            (b) =>
              `<article class="saved-booking"><div><span class="status-pill ${b.status === "cancelled" ? "cancelled" : ""}">${b.status === "cancelled" ? "Отменена" : "Демо · подтверждена"}</span><h3>${escape(b.resortName)}</h3><p>${escape(b.roomName)} · ${escape(b.tariffName)}</p><p class="small muted">${formatDate(b.start)} — ${formatDate(b.end)} · ${b.guests} гостя</p><strong>${money(b.total)}</strong></div>${b.status === "confirmed" ? `<button class="text-button danger" data-cancel="${escape(b.id)}">Отменить бронь</button>` : ""}</article>`,
          )
          .join("")
      : '<div class="empty-state"><h3>Здесь будет ваш следующий отдых</h3><p>Выберите санаторий на карте и сохраните первую демо-бронь.</p></div>';
}
function cancelBooking(id) {
  try {
    const latest = readBookings();
    const next = latest.map((b) =>
      b.id === id ? { ...b, status: "cancelled" } : b,
    );
    writeBookings(next);
    bookings = next;
    renderBookings();
    renderList();
    renderDetails();
    toast("Демо-бронь отменена. Номер снова доступен.");
    $("#bookings-dialog [data-close]").focus();
  } catch {
    toast("Не удалось отменить бронь: хранилище браузера недоступно.");
  }
}
$("#search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const next = {
    start: $("#check-in").value,
    end: $("#check-out").value,
    guests: Number($("#guests").value),
  };
  const error = validateSearch(next);
  $("#search-error").hidden = !error;
  $("#search-error").textContent = error;
  if (error) return;
  search = next;
  renderList();
  renderDetails();
  map.reset();
});
$("#check-in").addEventListener("change", () => {
  $("#check-out").min = $("#check-in").value;
});
["room-class", "sort", "available-only"].forEach((id) =>
  $("#" + id).addEventListener("change", () => {
    renderList();
    renderDetails();
  }),
);
$("#map-reset").addEventListener("click", () => map.reset());
$("#bookings-open").addEventListener("click", () => {
  syncStorage();
  renderBookings();
  openDialog("#bookings-dialog");
});
document.addEventListener("click", (event) => {
  const resort = event.target.closest("[data-resort]");
  if (resort) selectResort(resort.dataset.resort);
  const close = event.target.closest("[data-close]");
  if (close) closeDialog("#" + close.dataset.close);
  const cancel = event.target.closest("[data-cancel]");
  if (cancel) cancelBooking(cancel.dataset.cancel);
  if (event.target.closest("#details-close")) closeDetails();
  if (event.target.closest("#start-booking")) openBooking();
  if (event.target.closest("#reset-filters")) {
    $("#query").value = "";
    $("#room-class").value = "all";
    $("#available-only").checked = false;
    renderList();
    renderDetails();
    map.reset();
  }
});
$("#details").addEventListener("change", (event) => {
  if (event.target.name === "room") roomId = event.target.value;
  else if (event.target.name === "tariff") tariffId = event.target.value;
  else return;
  const name = event.target.name;
  const value = event.target.value;
  const scroll = $("#details").scrollTop;
  renderDetails();
  $("#details").scrollTop = scroll;
  $(`input[name="${name}"][value="${value}"]`).focus({ preventScroll: true });
});
$("#booking-dialog").addEventListener("submit", confirmBooking);
document.addEventListener("keydown", (event) => {
  if (
    event.key === "Escape" &&
    selectedId &&
    !document.querySelector("dialog[open]")
  )
    closeDetails();
});
window.addEventListener("storage", (event) => {
  if (event.key === storageKey) {
    syncStorage();
    renderList();
    renderDetails();
    if ($("#bookings-dialog").open) renderBookings();
  }
});
renderList();
map.reset();
