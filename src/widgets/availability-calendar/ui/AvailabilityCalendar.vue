<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { propertyToday, shiftDay } from "@/entities/booking";
import { request } from "@/shared/api";

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
const firstMonth = computed(() => today.value.slice(0, 7));
const lastMonth = computed(() => shiftDay(today.value, 365).slice(0, 7));
let generation = 0;
async function load() {
  const run = ++generation;
  data.value = null;
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
    (anchor.value ? day.departureRooms > 0 : day.availableRooms > 0)
  );
}
function select(day) {
  if (!selectable(day)) return;
  if (!anchor.value) anchor.value = day.date;
  else {
    emit("select", { start: anchor.value, end: day.date });
    anchor.value = "";
  }
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
  return `${date}: ${state}`;
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
    load();
  },
);
watch(
  () => [props.start, props.end],
  () => {
    anchor.value = "";
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
      <p class="availability-prompt" aria-live="polite">
        {{
          loading
            ? t("public.calendar.loading")
            : anchor
              ? t("public.calendar.selectDeparture", { date: anchor })
              : t("public.calendar.selectArrival")
        }}
        <button
          v-if="anchor"
          type="button"
          class="text-button"
          @click="anchor = ''"
        >
          {{ t("public.calendar.restart") }}
        </button>
      </p>
      <div v-if="failed" class="availability-error" role="alert">
        <p>{{ t("public.calendar.error") }}</p>
        <button type="button" @click="load">
          {{ t("public.calendar.retry") }}
        </button>
      </div>
      <template v-else-if="data">
        <p v-if="!data.totalRooms" class="field-help">
          {{ t("public.calendar.noRooms") }}
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
            v-for="empty in padding"
            :key="`empty-${empty}`"
            aria-hidden="true"
          ></span>
          <button
            v-for="day in data.days"
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
            }"
            @click="select(day)"
          >
            <span>{{ Number(day.date.slice(-2)) }}</span>
            <small aria-hidden="true">{{
              anchor && day.departureRooms
                ? "↗"
                : !day.bookable
                  ? "—"
                  : day.availableRooms
                    ? "•"
                    : "×"
            }}</small>
          </button>
        </div>
      </template>
      <div v-else class="availability-placeholder" aria-hidden="true"></div>
      <div class="availability-legend">
        <span>🟢 {{ t("public.calendar.free") }}</span
        ><span>× {{ t("public.calendar.busy") }}</span>
      </div>
      <p class="field-help">
        {{ t(roomId ? "public.calendar.roomHint" : "public.calendar.hint") }}
      </p>
    </template>
  </section>
</template>

<style scoped>
.availability-calendar {
  padding: 18px;
  margin: 18px 0;
  border: 1px solid #dbe4de;
  border-radius: 18px;
  background: #fff;
  width: 100%;
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
  font-size: 16px;
  margin: 0;
}
.availability-month {
  margin-top: 14px;
  text-transform: capitalize;
}
.availability-month button {
  border: 1px solid #dbe4de;
  border-radius: 10px;
  background: #f7faf8;
  width: 40px;
  height: 40px;
  font-size: 24px;
}
.availability-prompt {
  min-height: 38px;
  font-size: 12px;
  line-height: 1.5;
  color: #45584e;
}
.availability-prompt button {
  display: block;
  padding: 0;
  border: 0;
  background: transparent;
  text-decoration: underline;
  color: #285e46;
}
.availability-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 4px;
}
.availability-weekday {
  text-align: center;
  font-size: 11px;
  color: #617267;
  padding-bottom: 8px;
}
.availability-grid button {
  border: 1px solid transparent;
  border-radius: 9px;
  background: #f4f5f4;
  color: #929c96;
  min-height: 42px;
  padding: 5px 0 2px;
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
.availability-grid .free {
  background: #eaf5ec;
  color: #28673d;
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
  gap: 16px;
  font-size: 11px;
  margin-top: 14px;
  color: #45584e;
}
.availability-calendar .field-help {
  margin-bottom: 0;
  font-size: 11px;
  line-height: 1.5;
}
.availability-placeholder {
  min-height: 250px;
}
.availability-error {
  padding: 16px 0;
  font-size: 13px;
}
</style>
