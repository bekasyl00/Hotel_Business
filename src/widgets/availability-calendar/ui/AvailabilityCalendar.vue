<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { propertyToday, shiftDay } from "@/entities/booking";
import { request } from "@/shared/api";
import { money } from "@/shared/lib";
import { calendarDayPrice, compactCalendarPrice } from "../model/price.js";

const props = defineProps({
  resortId: { type: String, required: true },
  category: { type: String, required: true },
  roomId: { type: String, default: "" },
  guests: { type: Number, default: 2 },
  timeZone: { type: String, default: "Asia/Almaty" },
  start: { type: String, default: "" },
  end: { type: String, default: "" },
});
const emit = defineEmits(["select"]);
const { t, locale } = useI18n();
const today = computed(
  () => data.value?.today || propertyToday(props.timeZone),
);
const initialToday = propertyToday(props.timeZone);
const month = ref(
  props.start >= initialToday && props.start <= shiftDay(initialToday, 365)
    ? props.start.slice(0, 7)
    : initialToday.slice(0, 7),
);
const anchor = ref(""),
  data = ref(null),
  loading = ref(false),
  failed = ref(false);
const hasClass = computed(() =>
  ["standard", "comfort", "suite"].includes(props.category),
);
const validGuests = computed(
  () =>
    Number.isInteger(props.guests) && props.guests >= 1 && props.guests <= 4,
);
const monthDate = computed(() => new Date(`${month.value}-01T12:00:00Z`));
const monthLabel = computed(
  () =>
    `${t(`public.calendar.month${monthDate.value.getUTCMonth() + 1}`)} ${monthDate.value.getUTCFullYear()}`,
);
const weekdays = computed(() =>
  Array.from({ length: 7 }, (_, i) => t(`public.calendar.weekday${i}`)),
);
const padding = computed(() => (monthDate.value.getUTCDay() + 6) % 7);
const leadingDays = computed(() =>
  Array.from({ length: padding.value }, (_, index) =>
    Number(shiftDay(`${month.value}-01`, index - padding.value).slice(-2)),
  ),
);
const firstMonth = computed(() => today.value.slice(0, 7));
const lastMonth = computed(() => shiftDay(today.value, 365).slice(0, 7));
const previewDate = ref(props.start);
const calendarIdentity = computed(() =>
  JSON.stringify([
    props.resortId,
    props.category,
    props.roomId,
    props.guests,
    props.timeZone,
    month.value,
  ]),
);
const emptyDays = computed(() => {
  const count = new Date(
    Date.UTC(
      monthDate.value.getUTCFullYear(),
      monthDate.value.getUTCMonth() + 1,
      0,
    ),
  ).getUTCDate();
  return Array.from({ length: count }, (_, index) => ({
    date: `${month.value}-${String(index + 1).padStart(2, "0")}`,
    bookable: false,
    availableRooms: 0,
  }));
});
const priceDays = computed(() =>
  (data.value?.days || emptyDays.value).map((day) => ({
    ...day,
    priceDisplay: calendarDayPrice(day),
  })),
);
const trailingDays = computed(
  () => (7 - ((padding.value + priceDays.value.length) % 7)) % 7,
);
const selectedPriceDay = computed(() =>
  priceDays.value.find(
    (day) =>
      day.date === (anchor.value || previewDate.value || props.start) &&
      day.priceDisplay,
  ),
);
let generation = 0;
let dataIdentity = "";
async function load() {
  const run = ++generation;
  if (dataIdentity !== calendarIdentity.value) data.value = null;
  dataIdentity = calendarIdentity.value;
  failed.value = false;
  loading.value = false;
  if (!hasClass.value || !validGuests.value) return;
  loading.value = true;
  const query = new URLSearchParams({
    resortId: props.resortId,
    category: props.category,
    month: month.value,
    guests: props.guests,
  });
  if (props.roomId) query.set("roomId", props.roomId);
  if (anchor.value) query.set("arrival", anchor.value);
  try {
    const result = await request("GET", `/availability-calendar?${query}`);
    if (run === generation) data.value = result;
  } catch {
    if (run === generation) failed.value = true;
  } finally {
    if (run === generation) loading.value = false;
  }
}
function moveMonth(offset) {
  const d = monthDate.value;
  month.value = new Date(
    Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + offset, 1),
  )
    .toISOString()
    .slice(0, 7);
}
function selectable(day) {
  return (
    !loading.value &&
    !failed.value &&
    (anchor.value ? day.departureRooms > 0 : day.availableRooms > 0)
  );
}
function select(day) {
  if (!selectable(day)) return;
  if (!anchor.value) {
    previewDate.value = day.date;
    anchor.value = day.date;
  } else {
    emit("select", { start: anchor.value, end: day.date });
    anchor.value = "";
  }
}
function preview(day) {
  if (!anchor.value && day.priceDisplay) previewDate.value = day.date;
}
function priceText(day) {
  return t(
    props.roomId
      ? "public.calendar.nightPrice"
      : "public.calendar.classNightPrice",
    {
      amount: money(day.priceDisplay.amount),
    },
  );
}
function shortDate(date) {
  return new Intl.DateTimeFormat(locale.value, {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(`${date}T12:00:00Z`));
}
function restart() {
  anchor.value = "";
}
function label(day) {
  const date = new Intl.DateTimeFormat(locale.value, {
    day: "numeric",
    month: locale.value === "kk" ? "2-digit" : "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${day.date}T12:00:00Z`));
  const state =
    anchor.value && day.departureRooms > 0
      ? t("public.calendar.departure", { count: day.departureRooms })
      : !day.bookable
        ? t("public.calendar.unavailable")
        : day.availableRooms
          ? t("public.calendar.freeCount", { count: day.availableRooms })
          : t("public.calendar.busy");
  const price = day.priceDisplay;
  return `${date}: ${state}${price ? `; ${priceText(day)}${price.kind !== "regular" ? `; ${t(`public.calendar.${price.kind}`)}` : ""}` : ""}`;
}
function inRange(day) {
  return !anchor.value && props.start <= day && day <= props.end;
}
watch(
  () => [
    props.resortId,
    props.category,
    props.roomId,
    props.guests,
    props.timeZone,
  ],
  () => {
    anchor.value = "";
    previewDate.value = "";
    load();
  },
);
watch(
  () => [props.start, props.end],
  () => {
    anchor.value = "";
    previewDate.value = props.start;
  },
);
watch([month, anchor], load, { immediate: true });
onBeforeUnmount(() => generation++);
</script>

<template>
  <section
    class="availability-calendar"
    :aria-label="
      t(roomId ? 'public.calendar.roomTitle' : 'public.calendar.title')
    "
    :aria-busy="loading"
  >
    <div class="availability-title">
      <h3>
        {{ t(roomId ? "public.calendar.roomTitle" : "public.calendar.title") }}
      </h3>
      <span v-if="hasClass" class="small muted">{{
        t(`public.${category}`)
      }}</span>
    </div>
    <p v-if="!hasClass" class="field-help">
      {{ t("public.calendar.chooseClass") }}
    </p>
    <p v-else-if="!validGuests" class="field-help">
      {{ t("public.calendar.chooseGuests") }}
    </p>
    <template v-else>
      <div class="availability-month">
        <button
          type="button"
          :aria-label="t('public.calendar.previous')"
          :disabled="month <= firstMonth"
          @click="moveMonth(-1)"
        >
          ‹
        </button>
        <strong>{{ monthLabel }}</strong>
        <button
          type="button"
          :aria-label="t('public.calendar.next')"
          :disabled="month >= lastMonth"
          @click="moveMonth(1)"
        >
          ›
        </button>
      </div>
      <div class="availability-prompt">
        <p aria-live="polite">
          {{
            anchor
              ? t("public.calendar.selectDeparture", {
                  date: shortDate(anchor),
                })
              : t("public.calendar.selectArrival")
          }}
        </p>
        <button
          type="button"
          class="text-button"
          :disabled="!anchor"
          :aria-label="t('public.calendar.restart')"
          :title="t('public.calendar.restart')"
          @click="restart"
        >
          <span aria-hidden="true">↺</span>
        </button>
      </div>
      <p v-if="data && !data.totalRooms" class="field-help">
        {{ t("public.calendar.noRooms") }}
      </p>
      <p class="availability-price-caption">
        {{
          t(
            roomId
              ? "public.calendar.priceCaption"
              : "public.calendar.classPriceCaption",
          )
        }}
        <span v-if="loading" class="calendar-loading" role="status">
          <span class="calendar-sr-only">{{
            t("public.calendar.loading")
          }}</span>
        </span>
      </p>
      <div class="availability-grid">
        <span
          v-for="(day, index) in weekdays"
          :key="`weekday-${index}`"
          class="availability-weekday"
          aria-hidden="true"
          >{{ day }}</span
        >
        <span
          v-for="day in leadingDays"
          :key="`leading-${day}`"
          class="calendar-padding-day"
          aria-hidden="true"
          >{{ day }}</span
        >
        <button
          v-for="day in priceDays"
          :key="day.date"
          type="button"
          :disabled="!selectable(day)"
          :aria-label="label(day)"
          :title="label(day)"
          :aria-pressed="day.date === anchor || inRange(day.date)"
          :class="{
            free: day.availableRooms > 0,
            busy: day.bookable && !day.availableRooms,
            departure: anchor && day.departureRooms > 0,
            selected: day.date === anchor || inRange(day.date),
            endpoint:
              day.date === anchor ||
              (!anchor && [start, end].includes(day.date)),
            discount: day.priceDisplay?.kind === 'discount',
            seasonal: day.priceDisplay?.kind === 'seasonal',
          }"
          @click="select(day)"
          @focus="preview(day)"
        >
          <span class="calendar-day-number"
            >{{ Number(day.date.slice(-2))
            }}<span
              v-if="
                day.priceDisplay &&
                (day.priceDisplay.kind !== 'regular' ||
                  (anchor && day.departureRooms > 0))
              "
              class="calendar-kind-mark"
              aria-hidden="true"
              >{{
                anchor && day.departureRooms > 0
                  ? "↗"
                  : day.priceDisplay.kind === "discount"
                    ? "↓"
                    : "~"
              }}</span
            ></span
          >
          <small
            v-if="day.priceDisplay"
            class="calendar-day-price"
            aria-hidden="true"
            >{{ compactCalendarPrice(day.priceDisplay.amount, locale) }}</small
          >
          <small v-else aria-hidden="true">{{
            anchor && day.departureRooms
              ? "↗"
              : !day.bookable
                ? "—"
                : day.availableRooms
                  ? "•"
                  : "×"
          }}</small>
        </button>
        <span
          v-for="day in trailingDays"
          :key="`trailing-${day}`"
          class="calendar-padding-day"
          aria-hidden="true"
          >{{ day }}</span
        >
      </div>
      <div
        v-if="selectedPriceDay"
        class="calendar-price-detail"
        :class="selectedPriceDay.priceDisplay.kind"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        <span
          >{{
            t("public.calendar.nightOf", {
              date: shortDate(selectedPriceDay.date),
            })
          }}<small v-if="selectedPriceDay.priceDisplay.kind !== 'regular'">
            ·
            {{
              t(`public.calendar.${selectedPriceDay.priceDisplay.kind}`)
            }}</small
          ></span
        >
        <div>
          <del v-if="selectedPriceDay.priceDisplay.kind === 'discount'"
            ><span class="calendar-sr-only"
              >{{ t("public.calendar.previousPrice") }} </span
            >{{ money(selectedPriceDay.priceDisplay.regular) }}</del
          ><strong>{{ priceText(selectedPriceDay) }}</strong>
        </div>
      </div>
      <div v-if="failed" class="availability-error" role="alert">
        <p>{{ t("public.calendar.error") }}</p>
        <button type="button" @click="load">
          {{ t("public.calendar.retry") }}
        </button>
      </div>
      <div class="availability-legend">
        <span class="legend-free">● {{ t("public.calendar.free") }}</span>
        <span>× {{ t("public.calendar.busy") }}</span>
        <span
          v-if="priceDays.some((day) => day.priceDisplay?.kind === 'discount')"
          class="legend-discount"
          >↓ {{ t("public.calendar.discount") }}</span
        >
        <span
          v-if="priceDays.some((day) => day.priceDisplay?.kind === 'seasonal')"
          class="legend-seasonal"
          >~ {{ t("public.calendar.seasonal") }}</span
        >
      </div>
      <details class="availability-help">
        <summary>{{ t("public.calendar.howToRead") }}</summary>
        <p class="field-help">
          {{ t(roomId ? "public.calendar.roomHint" : "public.calendar.hint") }}
        </p>
        <p class="field-help">{{ t("public.calendar.compactHint") }}</p>
      </details>
    </template>
  </section>
</template>

<style scoped>
.availability-calendar {
  padding: 12px;
  margin: 12px 0;
  border: 1px solid #dbe4de;
  border-radius: 14px;
  background: #fff;
  width: 100%;
  min-width: 0;
  max-width: 460px;
  box-sizing: border-box;
}
.availability-title,
.availability-month {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.availability-title h3 {
  font-size: 15px;
  line-height: 1.4;
  margin: 0;
}
.availability-title .small {
  flex-shrink: 0;
  font-size: 11px;
}
.availability-month {
  margin-top: 6px;
  text-transform: capitalize;
}
.availability-month strong {
  font-size: 15px;
}
.availability-month button {
  border: 1px solid #dbe4de;
  border-radius: 10px;
  background: #f7faf8;
  flex: 0 0 44px;
  width: 44px;
  height: 44px;
  font-size: 20px;
  padding: 0;
}
.availability-prompt {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 44px;
  align-items: center;
  min-height: 44px;
  font-size: 12px;
  line-height: 1.5;
  color: #45584e;
}
.availability-prompt button {
  width: 44px;
  min-height: 44px;
  padding: 0;
  border: 0;
  background: transparent;
  border-radius: 8px;
  font-size: 20px;
  color: #285e46;
}
.availability-prompt button:disabled {
  visibility: hidden;
}
.availability-prompt p {
  margin: 0;
  line-height: 1.4;
}
.availability-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 3px;
  width: 100%;
  min-width: 0;
}
.availability-weekday {
  text-align: center;
  font-size: 11px;
  color: #617267;
  padding-bottom: 5px;
}
.calendar-padding-day {
  display: grid;
  place-items: center;
  min-height: 46px;
  border-radius: 9px;
  background: #fafbf9;
  color: #abb3ac;
  font-size: 13px;
}
.availability-grid button {
  appearance: none;
  -webkit-appearance: none;
  min-width: 0;
  border: 1px solid transparent;
  border-radius: 9px;
  background: #f4f5f4;
  color: #929c96;
  width: 100%;
  min-height: 46px;
  padding: 4px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font: inherit;
  font-size: 13px;
  line-height: 1.1;
}
.availability-grid button small {
  font-size: 10px;
  margin-top: 3px;
}
.availability-grid .calendar-day-price {
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  white-space: nowrap;
  letter-spacing: -0.03em;
  max-width: 100%;
}
.calendar-day-number {
  display: flex;
  align-items: center;
  gap: 2px;
}
.calendar-kind-mark {
  font-size: 10px;
  font-weight: 700;
}
.availability-price-caption {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  color: #45584e;
  margin: 0 0 8px;
}
.calendar-loading {
  flex-shrink: 0;
  width: 12px;
  height: 12px;
  border: 2px solid #dbe4de;
  border-top-color: #285e46;
  border-radius: 50%;
  animation: calendar-loading 0.8s linear infinite;
}
@keyframes calendar-loading {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .calendar-loading {
    animation: none;
  }
}
.calendar-price-detail {
  display: grid;
  gap: 4px;
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: #f3f6f4;
  font-size: 11px;
}
.calendar-price-detail > div {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
}
.calendar-price-detail strong {
  font-size: 13px;
}
.calendar-price-detail del {
  color: #657168;
}
.calendar-price-detail.discount {
  background: #eaf5ec;
  color: #176538;
}
.calendar-price-detail.seasonal {
  background: #fff4e3;
  color: #845410;
}
.calendar-price-detail small {
  font-size: inherit;
}
.calendar-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.availability-grid .free {
  background: #eaf5ec;
  color: #28673d;
}
.availability-grid .free.discount {
  background: #dff1e3;
  color: #176538;
}
.availability-grid .free.seasonal {
  background: #fff1d9;
  color: #845410;
}
.availability-grid .busy {
  background: #fbeeed;
  color: #9f4541;
}
.availability-grid .selected {
  box-shadow: inset 0 0 0 1px #439571;
}
.availability-grid .departure {
  border-color: #285e46;
}
.availability-grid .endpoint.free {
  background: #24593f;
  color: white;
}
.availability-grid button:disabled {
  cursor: default;
  opacity: 1;
}
.availability-grid button:not(:disabled):hover {
  box-shadow: inset 0 0 0 2px #24593f;
}
.availability-calendar button:focus-visible {
  outline: 3px solid #4579d2;
  outline-offset: 2px;
}
.availability-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  font-size: 11px;
  margin-top: 10px;
  color: #45584e;
}
.legend-free {
  color: #28673d;
}
.legend-discount {
  color: #176538;
  font-weight: 600;
}
.legend-seasonal {
  color: #845410;
}
.availability-help {
  margin-top: 6px;
  color: #45584e;
  font-size: 11px;
}
.availability-help summary {
  cursor: pointer;
  min-height: 24px;
  padding: 4px 0;
}
.availability-help summary:focus-visible {
  outline: 3px solid #4579d2;
  outline-offset: 2px;
}
.availability-calendar .field-help {
  margin-bottom: 0;
  font-size: 11px;
  line-height: 1.5;
}
.availability-error {
  padding: 16px 0;
  font-size: 13px;
}
@media (max-width: 380px) {
  .availability-calendar {
    padding: 10px 8px;
  }
  .availability-grid {
    gap: 2px;
  }
}
</style>
