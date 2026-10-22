<script setup>
import {
  ref,
  reactive,
  computed,
  onMounted,
  onBeforeUnmount,
  watch,
} from "vue";
import { useResortStore } from "@/entities/resort";
import {
  useBookingStore,
  dateAfter,
  validateSearch,
  nightsBetween,
} from "@/entities/booking";
import { BookingEditor } from "@/features/create-booking";
import { Modal, GeoMap } from "@/shared/ui";
import { request } from "@/shared/api";
import { money, dateLabel, categoryNames } from "@/shared/lib";
const catalog = useResortStore(),
  bookings = useBookingStore();
const draft = reactive({ start: dateAfter(7), end: dateAfter(10), guests: 2 }),
  search = ref({ ...draft });
const query = ref(""),
  category = ref("all"),
  sort = ref("recommended"),
  onlyAvailable = ref(true),
  available = ref([]),
  selected = ref(null),
  roomId = ref(""),
  tariffId = ref(""),
  loading = ref(true),
  error = ref(""),
  searchError = ref(""),
  notice = ref(""),
  checkout = ref(false),
  success = ref(null),
  showBookings = ref(false),
  cancelTarget = ref(null),
  cancelError = ref(""),
  busy = ref(false);
const map = ref();
let generation = 0;
const resort = computed(() =>
  catalog.resorts.find((r) => r.id === selected.value),
);
const roomsFor = (id) =>
  catalog.rooms.filter(
    (r) =>
      r.resortId === id &&
      (category.value === "all" || r.category === category.value),
  );
const freeFor = (id) =>
  roomsFor(id).filter((r) => available.value.includes(r.id));
const filtered = computed(() => {
  let result = catalog.resorts
    .filter((r) =>
      `${r.name} ${r.city} ${r.address}`
        .toLocaleLowerCase()
        .includes(query.value.toLocaleLowerCase()),
    )
    .map((r) => ({
      ...r,
      free: freeFor(r.id).length,
      price: Math.min(...freeFor(r.id).map((x) => x.price)),
    }));
  if (onlyAvailable.value) result = result.filter((r) => r.free > 0);
  if (sort.value === "price") result.sort((a, b) => a.price - b.price);
  if (sort.value === "rating") result.sort((a, b) => b.rating - a.rating);
  return result;
});
const points = computed(() =>
  filtered.value.map((r) => ({
    ...r,
    label: r.free ? money(r.price) : "Нет мест",
  })),
);
const room = computed(() => catalog.rooms.find((r) => r.id === roomId.value));
const tariffs = computed(() =>
  catalog.tariffs.filter((t) => t.resortId === selected.value),
);
const tariff = computed(() =>
  tariffs.value.find((t) => t.id === tariffId.value),
);
const total = computed(() =>
  room.value && tariff.value
    ? (room.value.price + tariff.value.supplement * search.value.guests) *
      nightsBetween(search.value.start, search.value.end)
    : 0,
);
function choose(id) {
  selected.value = id;
  roomId.value = freeFor(id)[0]?.id || "";
  tariffId.value = catalog.tariffs.find((t) => t.resortId === id)?.id || "";
}
function reset() {
  query.value = "";
  category.value = "all";
  onlyAvailable.value = false;
}
async function load() {
  const run = ++generation;
  loading.value = true;
  error.value = "";
  try {
    const data = await request("GET", "/catalog");
    const response = await request(
      "GET",
      "/availability?" + new URLSearchParams(search.value),
    );
    const mine = await request("GET", "/my-bookings");
    if (run !== generation) return;
    catalog.setData(data);
    bookings.items = mine;
    available.value = response.roomIds;
    if (selected.value && !resort.value) selected.value = null;
    if (!available.value.includes(roomId.value))
      roomId.value = freeFor(selected.value)[0]?.id || "";
    if (!tariffs.value.some((t) => t.id === tariffId.value))
      tariffId.value = tariffs.value[0]?.id || "";
  } catch (e) {
    if (run === generation) error.value = e.message;
  } finally {
    if (run === generation) loading.value = false;
  }
}
async function find() {
  searchError.value = validateSearch(draft);
  if (searchError.value) return;
  search.value = { ...draft };
  await load();
  map.value?.reset();
}
async function saved(booking) {
  checkout.value = false;
  success.value = booking;
  await load();
}
async function openMyBookings() {
  showBookings.value = true;
  notice.value = "";
  try {
    await bookings.loadMine();
  } catch (e) {
    notice.value = e.message;
  }
}
async function cancel() {
  cancelError.value = "";
  busy.value = true;
  try {
    await bookings.cancel(cancelTarget.value);
    cancelTarget.value = null;
    notice.value = "Бронь отменена. Номер снова доступен.";
    await load();
  } catch (e) {
    cancelError.value = e.message;
  } finally {
    busy.value = false;
  }
}
watch(category, () => {
  if (!freeFor(selected.value).some((r) => r.id === roomId.value))
    roomId.value = freeFor(selected.value)[0]?.id || "";
});
const changed = (e) => {
  if (e.key === "tynys:workspace:v2") load();
};
onMounted(() => {
  load();
  window.addEventListener("storage", changed);
});
onBeforeUnmount(() => {
  generation++;
  window.removeEventListener("storage", changed);
});
</script>
<template>
  <div class="public-site">
    <a class="skip-link" href="#results">К списку санаториев</a>
    <header class="header">
      <RouterLink class="brand" to="/"
        ><img src="/assets/logo.svg" alt="" width="36" height="36" /><span
          >тыныс<span class="brand-dot">.</span></span
        ></RouterLink
      >
      <nav aria-label="Основная навигация">
        <span class="nav-current">Санатории</span
        ><button class="text-button" @click="openMyBookings">
          Мои бронирования
          <span class="count">{{
            bookings.items.filter((b) => b.status === "confirmed").length
          }}</span>
        </button>
      </nav>
      <RouterLink class="staff-link" to="/staff"
        >Кабинет сотрудника ↗</RouterLink
      ><span class="demo-badge">Демо</span>
    </header>
    <section class="search-bar" aria-label="Поиск отдыха">
      <form @submit.prevent="find">
        <label class="destination"
          ><span>Куда отправимся</span
          ><input
            v-model="query"
            type="search"
            placeholder="Сарыагаш, санаторий…" /></label
        ><label
          ><span>Заезд</span
          ><input
            v-model="draft.start"
            type="date"
            :min="dateAfter()"
            required /></label
        ><label
          ><span>Выезд</span
          ><input
            v-model="draft.end"
            type="date"
            :min="draft.start"
            required /></label
        ><label
          ><span>Гости</span
          ><select v-model.number="draft.guests">
            <option v-for="n in 4" :value="n" :key="n">
              {{ n }} {{ n === 1 ? "взрослый" : "взрослых" }}
            </option>
          </select></label
        ><button class="primary search-submit" :disabled="loading">
          {{ loading ? "Загружаем…" : "⌕ Найти отдых" }}
        </button>
      </form>
      <p v-if="searchError" class="form-error" role="alert">
        {{ searchError }}
      </p>
    </section>
    <div v-if="error" class="error-panel" role="alert">
      {{ error }} <button class="secondary" @click="load">Повторить</button>
    </div>
    <main class="workspace">
      <aside class="results-panel" id="results" tabindex="-1">
        <div class="results-heading">
          <span class="eyebrow">ЮГ КАЗАХСТАНА</span>
          <h1>Санатории Сарыагаша</h1>
          <p role="status">
            {{
              loading
                ? "Обновляем наличие…"
                : filtered.length +
                  " санаториев · " +
                  search.guests +
                  " гостя · найдите свой ритм"
            }}
          </p>
        </div>
        <div class="filters">
          <label class="filter-select"
            ><span class="sr-only">Категория номера</span
            ><select v-model="category">
              <option value="all">Все категории</option>
              <option
                v-for="(name, key) in categoryNames"
                :key="key"
                :value="key"
              >
                {{ name }}
              </option>
            </select></label
          ><label class="filter-select"
            ><span class="sr-only">Сортировка</span
            ><select v-model="sort">
              <option value="recommended">Рекомендуем</option>
              <option value="price">Сначала дешевле</option>
              <option value="rating">По рейтингу</option>
            </select></label
          >
        </div>
        <label class="available-filter"
          ><input v-model="onlyAvailable" type="checkbox" />Только со свободными
          номерами</label
        >
        <div class="resort-list">
          <article
            v-for="(r, i) in filtered"
            :key="r.id"
            :class="['resort-card', { active: selected === r.id }]"
          >
            <button
              class="resort-card-button"
              :aria-label="'Выбрать санаторий ' + r.name"
              @click="choose(r.id)"
            >
              <div :class="['resort-photo', 'photo-' + (i % 3)]">
                <img
                  src="/assets/resort.jpg"
                  alt="Иллюстрация курортного отеля"
                  :loading="i > 1 ? 'lazy' : 'eager'"
                />
              </div>
              <div class="resort-info">
                <div class="card-title-row">
                  <h2>{{ r.name }}</h2>
                  <span class="rating">{{
                    r.rating ? "★ " + r.rating : "Новый"
                  }}</span>
                </div>
                <p class="resort-location">{{ r.city }} · {{ r.address }}</p>
                <p class="resort-subtitle">{{ r.subtitle }}</p>
                <div class="amenity-line">
                  <span>♧ {{ r.feature }}</span
                  ><span>Wi-Fi</span>
                </div>
                <div class="card-bottom">
                  <span :class="['availability', { 'sold-out': !r.free }]">{{
                    r.free
                      ? r.free + " номеров доступны"
                      : "Нет мест на эти даты"
                  }}</span
                  ><span class="card-price"
                    >{{ r.free ? money(r.price) : "Другие даты →"
                    }}<small v-if="r.free"> / ночь</small></span
                  >
                </div>
              </div>
            </button>
          </article>
          <div
            v-if="!filtered.length && !loading && !error"
            class="empty-state"
          >
            <h2>Пока ничего не нашлось</h2>
            <p>Измените даты или сбросьте фильтры.</p>
            <button class="secondary" @click="reset">Сбросить фильтры</button>
          </div>
        </div>
        <p class="data-note">
          Демонстрационные цены, рейтинги и наличие. Метки приблизительные,
          фотографии иллюстративные.
        </p>
      </aside>
      <section class="map-panel" aria-label="Карта санаториев">
        <GeoMap
          ref="map"
          :points="points"
          :selected="selected"
          @select="choose"
        />
        <div class="map-caption">
          <span class="live-dot"></span>Найдите своё место для отдыха
        </div>
        <div class="map-legend">Санатории · цена за номер / ночь</div>
      </section>
      <section
        v-if="resort"
        class="details-panel"
        aria-label="Выбранный санаторий"
      >
        <div class="detail-nav">
          <span>{{ resort.name }}</span
          ><button
            class="icon-button"
            aria-label="Закрыть санаторий"
            @click="selected = null"
          >
            ×
          </button>
        </div>
        <div class="detail-cover">
          <img
            src="/assets/resort.jpg"
            alt="Иллюстративное фото курорта"
          /><span class="photo-badge">{{ resort.city }}</span>
        </div>
        <div class="detail-body">
          <div class="card-title-row">
            <h2>{{ resort.name }}</h2>
            <span class="rating">{{
              resort.rating ? "★ " + resort.rating : "Новый"
            }}</span>
          </div>
          <p class="muted">{{ resort.subtitle }}</p>
          <p class="detail-description">{{ resort.description }}</p>
          <div class="step-title">
            <span>01</span>
            <h3>Выберите номер</h3>
          </div>
          <p class="small muted">
            {{ dateLabel(search.start) }} — {{ dateLabel(search.end) }} ·
            {{ search.guests }} гостя
          </p>
          <div class="room-options">
            <label
              v-for="r in roomsFor(resort.id)"
              :key="r.id"
              :class="[
                'room-option',
                {
                  chosen: roomId === r.id,
                  unavailable: !available.includes(r.id),
                },
              ]"
              ><input
                v-model="roomId"
                type="radio"
                name="room"
                :value="r.id"
                :disabled="!available.includes(r.id)"
              /><img src="/assets/room.jpg" alt="Иллюстрация номера" /><span
                class="room-copy"
                ><strong>{{ r.title }} · № {{ r.number }}</strong
                ><span class="small muted"
                  >{{ r.area }} м² · до {{ r.capacity }} гостей</span
                ><span class="small muted">{{ r.beds }}</span
                ><span class="room-bottom"
                  ><strong>{{ money(r.price) }}<small> / ночь</small></strong
                  ><span class="small">{{
                    available.includes(r.id)
                      ? "Свободен"
                      : r.capacity < search.guests
                        ? "Мало мест"
                        : "Занят"
                  }}</span></span
                ></span
              ></label
            >
          </div>
          <div v-if="room && tariffs.length">
            <div class="step-title">
              <span>02</span>
              <h3>Ваш формат отдыха</h3>
            </div>
            <div class="tariff-options">
              <label
                v-for="t in tariffs"
                :key="t.id"
                :class="['tariff-option', { chosen: tariffId === t.id }]"
                ><input
                  v-model="tariffId"
                  type="radio"
                  name="tariff"
                  :value="t.id"
                /><span
                  ><strong>{{ t.name }}</strong
                  ><span class="small muted">{{ t.description }}</span
                  ><span class="small">{{ t.features.join(" · ") }}</span></span
                ><b
                  >{{ t.supplement ? "+" + money(t.supplement) : "Включено"
                  }}<small>{{
                    t.supplement ? "за гостя / ночь" : "в цену номера"
                  }}</small></b
                ></label
              >
            </div>
          </div>
          <div v-else class="empty-state">
            <h3>Нет доступного предложения</h3>
            <p>Измените даты или выберите другой санаторий.</p>
          </div>
          <p class="data-note">
            Условия иллюстративные. Настоящий номер не резервируется.
          </p>
        </div>
        <div v-if="room && tariff" class="booking-footer">
          <div>
            <span class="small muted"
              >{{ nightsBetween(search.start, search.end) }} ночи ·
              {{ tariff.name }}</span
            ><strong>{{ money(total) }}</strong>
          </div>
          <button class="primary" :disabled="loading" @click="checkout = true">
            Выбрать →
          </button>
        </div>
      </section>
    </main>
    <BookingEditor
      v-if="checkout && resort"
      :resort="resort"
      :rooms="catalog.rooms.filter((r) => r.resortId === resort.id)"
      :tariffs="tariffs"
      :preset="{ ...search, roomId, tariffId }"
      @close="checkout = false"
      @saved="saved"
    />
    <Modal v-if="success" title="Демо-бронь создана" @close="success = null"
      ><div class="success-view">
        <div class="success-icon">✓</div>
        <h3>{{ success.resortName }}</h3>
        <p>{{ success.roomName }} · № {{ success.unit }}</p>
        <p>{{ dateLabel(success.start) }} — {{ dateLabel(success.end) }}</p>
        <strong>{{ money(success.total) }}</strong
        ><code>№ {{ success.id.slice(0, 8).toUpperCase() }}</code>
        <p class="field-help">
          Сохранено в «Моих бронированиях». Реальное бронирование не
          выполнялось.
        </p>
        <button class="primary full-width" @click="success = null">
          Продолжить поиск
        </button>
      </div></Modal
    >
    <Modal
      v-if="showBookings"
      title="Мои бронирования"
      @close="showBookings = false"
      ><p class="demo-note">Демо-брони сохраняются только в этом браузере.</p>
      <p v-if="notice" role="status" class="success-notice">{{ notice }}</p>
      <div v-if="!bookings.items.length" class="work-empty">
        <h3>Ваш отдых ещё впереди</h3>
        <p>Выберите санаторий на карте.</p>
      </div>
      <article
        v-for="b in [...bookings.items].reverse()"
        :key="b.id"
        class="saved-booking"
      >
        <div>
          <span :class="['status-pill', b.status]">{{
            b.status === "confirmed" ? "Демо · подтверждена" : "Отменена"
          }}</span>
          <h3>{{ b.resortName }}</h3>
          <p>{{ b.roomName }} · {{ b.tariffName }}</p>
          <p class="small muted">
            {{ dateLabel(b.start) }} — {{ dateLabel(b.end) }}
          </p>
          <strong>{{ money(b.total) }}</strong>
        </div>
        <button
          v-if="b.status === 'confirmed'"
          class="text-button danger"
          @click="
            cancelTarget = b;
            cancelError = '';
          "
        >
          Отменить бронь
        </button>
      </article></Modal
    >
    <Modal
      v-if="cancelTarget"
      title="Отменить бронь?"
      :busy="busy"
      @close="cancelTarget = null"
      ><p class="confirm-text">
        Номер освободится на выбранные даты. Запись останется в истории.
      </p>
      <p v-if="cancelError" class="form-error" role="alert">
        {{ cancelError }}
      </p>
      <div class="form-actions">
        <button class="secondary" :disabled="busy" @click="cancelTarget = null">
          Назад</button
        ><button class="danger-button" :disabled="busy" @click="cancel">
          {{ busy ? "Отменяем…" : "Отменить бронь" }}
        </button>
      </div></Modal
    >
  </div>
</template>
