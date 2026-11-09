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
    if (run === generation) {
      failed.value = true;
      data.value = null;
    }
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
  const state = !data.value
    ? t(loading.value ? "public.calendar.loading" : "public.calendar.unknown")
    : anchor.value && day.departureRooms > 0
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
          :aria-pressed="
            Boolean(data) && (day.date === anchor || inRange(day.date))
          "
          :class="{
            free: day.availableRooms > 0,
            busy: day.bookable && !day.availableRooms,
            departure: anchor && day.departureRooms > 0,
            selected: data && (day.date === anchor || inRange(day.date)),
            endpoint:
              data &&
              (day.date === anchor ||
                (!anchor && [start, end].includes(day.date))),
            unknown: !data,
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
                    : "◆"
              }}</span
            ></span
          >
          <small
            v-if="day.priceDisplay"
            class="calendar-day-price"
            aria-hidden="true"
            >{{ compactCalendarPrice(day.priceDisplay.amount, locale) }}</small
          >
          <small v-else-if="data" aria-hidden="true">{{
            anchor && day.departureRooms
              ? "↗"
              : !day.bookable
                ? "—"
                : day.availableRooms
                  ? "•"
                  : "—"
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
              selectedPriceDay.priceDisplay.periodLabel ||
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
        <span class="legend-free"
          ><i aria-hidden="true"></i>{{ t("public.calendar.free") }}</span
        >
        <span class="legend-busy"
          ><i aria-hidden="true"></i>{{ t("public.calendar.busy") }}</span
        >
        <span
          v-if="priceDays.some((day) => day.priceDisplay?.kind === 'discount')"
          class="legend-discount"
          ><i aria-hidden="true">↓</i>{{ t("public.calendar.discount") }}</span
        >
        <span
          v-if="priceDays.some((day) => day.priceDisplay?.kind === 'seasonal')"
          class="legend-seasonal"
          ><i aria-hidden="true">◆</i>{{ t("public.calendar.seasonal") }}</span
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
  box-sizing: border-box;
  width: 100%;
  max-width: 460px;
  min-width: 0;
  margin: 12px 0;
  padding: 14px;
  border: 1px solid #e7ebe7;
  border-radius: 16px;
  background: #fff;
  color: #263b2e;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.availability-title,
.availability-month {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.availability-title h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.3;
  letter-spacing: -0.01em;
}
.availability-title .small {
  flex-shrink: 0;
  font-size: 12px;
  color: #728076;
}
.availability-month {
  margin-top: 6px;
  text-transform: capitalize;
}
.availability-month strong {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.02em;
}
.availability-month button,
.availability-prompt button {
  appearance: none;
  -webkit-appearance: none;
  flex: 0 0 44px;
  width: 44px;
  height: 44px;
  min-height: 44px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: #34513d;
  font-size: 24px;
  font-weight: 400;
  box-shadow: none;
}
.availability-month button:disabled {
  opacity: 0.3;
}
.availability-prompt {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 36px;
  align-items: center;
  min-height: 36px;
  font-size: 12px;
  line-height: 1.4;
  color: #66766b;
}
.availability-prompt button {
  width: 36px;
  min-height: 36px;
  height: 36px;
  font-size: 20px;
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
  padding: 0 0 6px;
  text-align: center;
  font-size: 11px;
  color: #839087;
}
.calendar-padding-day {
  display: grid;
  place-items: center;
  min-height: 46px;
  color: #bec5c0;
  font-size: 14px;
}
.availability-grid button {
  appearance: none;
  -webkit-appearance: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  min-height: 46px;
  padding: 4px 0;
  border: 1px solid transparent;
  border-radius: 10px;
  background: #f7f8f7;
  color: #a1aaa4;
  box-shadow: none;
  font: inherit;
  font-size: 14px;
  font-weight: 400;
  line-height: 1.1;
  touch-action: manipulation;
  user-select: none;
  -webkit-user-select: none;
  transition:
    background-color 120ms ease-out,
    color 120ms ease-out;
}
.availability-grid button small {
  margin-top: 4px;
  font-size: 10px;
}
.availability-grid .calendar-day-price {
  max-width: 100%;
  font-size: 10px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  letter-spacing: -0.02em;
}
.calendar-day-number {
  display: flex;
  align-items: center;
  gap: 1px;
}
.calendar-kind-mark {
  font-size: 7px;
  font-weight: 500;
}
.availability-price-caption {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 0 0 10px;
  color: #839087;
  font-size: 11px;
  line-height: 1.3;
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
.calendar-price-detail {
  display: grid;
  gap: 3px;
  margin-top: 10px;
  padding: 9px 11px;
  border-radius: 10px;
  background: #f7f8f6;
  font-size: 12px;
  line-height: 1.35;
}
.calendar-price-detail > div {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 7px;
}
.calendar-price-detail strong {
  font-size: 14px;
  font-weight: 600;
}
.calendar-price-detail del {
  color: #839087;
  font-size: 12px;
}
.calendar-price-detail.discount {
  background: #f0f7f1;
  color: #326444;
}
.calendar-price-detail.seasonal {
  background: #fcf6ed;
  color: #816036;
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
  background: #f1f6f2;
  color: #3d6349;
}
.availability-grid .free.discount .calendar-day-price {
  color: #267843;
}
.availability-grid .free.seasonal {
  background: #fcf7ee;
  color: #816036;
}
.availability-grid .busy {
  background: #fbefef;
  color: #b05b5b;
}
.availability-grid .unknown {
  background: #fafbfa;
  color: #b4bcb6;
}
.availability-grid .selected {
  background: #e4eee6;
}
.availability-grid .departure {
  border-color: #bccfbe;
}
.availability-grid .endpoint {
  background: #34513d;
  color: white;
}
.availability-grid .endpoint .calendar-day-price {
  color: white;
}
.availability-grid button:disabled {
  cursor: default;
  opacity: 1;
}
.availability-calendar button:not(:disabled):active {
  background: #dfe9e1;
  color: #263b2e;
}
@media (hover: hover) and (pointer: fine) {
  .availability-calendar button:not(:disabled):hover {
    box-shadow: inset 0 0 0 1px #73937b;
  }
}
.availability-calendar button:focus-visible,
.availability-help summary:focus-visible {
  outline: 2px solid #4579d2;
  outline-offset: 2px;
}
.availability-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 7px 12px;
  margin-top: 12px;
  color: #66766b;
  font-size: 11px;
  line-height: 1.3;
}
.availability-legend > span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.availability-legend i {
  width: 7px;
  height: 7px;
  font-size: 9px;
  line-height: 7px;
  font-style: normal;
}
.legend-free i {
  background: #729d7e;
  border-radius: 50%;
}
.legend-busy i {
  background: #cc7c7c;
  border-radius: 2px;
}
.legend-discount {
  color: #267843;
}
.legend-seasonal {
  color: #816036;
}
.availability-help {
  margin-top: 2px;
  color: #7b887f;
  font-size: 11px;
}
.availability-help summary {
  cursor: pointer;
  min-height: 32px;
  padding: 8px 0 4px;
}
.availability-calendar .field-help {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.45;
}
.availability-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
  padding: 8px 10px;
  border-radius: 10px;
  background: #fcf6ed;
  color: #816036;
  font-size: 12px;
  line-height: 1.4;
}
.availability-error p {
  margin: 0;
}
.availability-error button {
  flex-shrink: 0;
  min-height: 40px;
  padding: 0 9px;
  border: 0;
  border-radius: 8px;
  color: #34513d;
  background: white;
  font: inherit;
  font-weight: 500;
}
@media (max-width: 380px) {
  .availability-calendar {
    padding: 12px 9px;
  }
  .availability-grid {
    gap: 2px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .calendar-loading {
    animation: none;
  }
  .availability-grid button {
    transition: none;
  }
}
</style>
