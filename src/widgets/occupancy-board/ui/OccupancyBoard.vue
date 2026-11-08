<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from "vue";
import { useI18n } from "vue-i18n";
import {
  shiftDay,
  propertyToday,
  occupancyState,
  calendarRows,
} from "@/entities/booking";
import { money } from "@/shared/lib";
const props = defineProps({
  rooms: Array,
  bookings: Array,
  resort: Object,
  busy: Boolean,
  readOnly: Boolean,
});
const emit = defineEmits(["select", "create", "refresh"]);
const { t, locale } = useI18n();
const now = ref(Date.now());
const today = computed(() =>
  propertyToday(props.resort?.timeZone, new Date(now.value)),
);
const start = ref(shiftDay(today.value, -2)),
  days = ref(14),
  query = ref(""),
  state = ref("all");
const states = ["past", "active", "reserved", "pending"];
const dates = computed(() =>
  Array.from({ length: days.value }, (_, i) => shiftDay(start.value, i)),
);
const rows = computed(() =>
  calendarRows(props.rooms, props.bookings, start.value, days.value, {
    query: query.value,
    state: state.value,
    now: now.value,
  }),
);
const fmt = (day, options) =>
  new Intl.DateTimeFormat(locale.value, { timeZone: "UTC", ...options }).format(
    new Date(`${day}T00:00:00Z`),
  );
const period = computed(
  () =>
    `${fmt(start.value, { day: "numeric", month: "long" })} — ${fmt(shiftDay(start.value, days.value - 1), { day: "numeric", month: "long", year: "numeric" })}`,
);
const liveBookings = computed(() =>
  props.bookings.filter((b) => occupancyState(b, now.value) !== "closed"),
);
const stats = computed(() => [
  ["roomsCount", props.rooms.length],
  [
    "living",
    liveBookings.value.filter((b) => occupancyState(b, now.value) === "active")
      .length,
  ],
  [
    "arrivals",
    liveBookings.value.filter(
      (b) =>
        b.start === today.value && occupancyState(b, now.value) === "reserved",
    ).length,
  ],
  [
    "departures",
    liveBookings.value.filter(
      (b) => b.end === today.value && occupancyState(b, now.value) === "active",
    ).length,
  ],
]);
const blockedDays = computed(() => {
  const result = new Map();
  for (const b of liveBookings.value) {
    if (!["pending", "confirmed"].includes(b.status)) continue;
    if (!result.has(b.roomId)) result.set(b.roomId, new Set());
    for (const day of dates.value)
      if (b.start <= day && day < b.end) result.get(b.roomId).add(day);
  }
  return result;
});
function available(room, day) {
  return (
    !props.readOnly &&
    room.status === "active" &&
    props.resort?.status === "published" &&
    day >= today.value &&
    !blockedDays.value.get(room.id)?.has(day)
  );
}
function create(room, day) {
  emit("create", {
    roomId: room.id,
    start: day,
    end: shiftDay(day, 1),
    guests: Math.min(2, room.capacity),
  });
}
const label = (b) =>
  `${b.guestLabel} · № ${b.unit} · ${b.start} — ${b.end} · ${money(b.paymentTerms?.total ?? b.total)}`;
let timer;
onMounted(() => {
  timer = setInterval(() => {
    now.value = Date.now();
  }, 30000);
});
onBeforeUnmount(() => clearInterval(timer));
</script>
<template>
  <section class="occupancy-board" :aria-label="t('staff.board.title')">
    <div class="board-summary">
      <div v-for="[key, value] in stats" :key="key">
        <span>{{ t(`staff.board.${key}`) }}</span
        ><strong>{{ value }}</strong
        ><small>{{
          key === "roomsCount" ? resort?.name : t("staff.board.today")
        }}</small>
      </div>
    </div>
    <div class="board-panel">
      <div class="board-toolbar">
        <div class="board-period">
          <button
            class="secondary"
            :aria-label="t('staff.board.previous')"
            @click="start = shiftDay(start, -days)"
          >
            ←</button
          ><button class="secondary" @click="start = shiftDay(today, -2)">
            {{ t("staff.board.today") }}</button
          ><button
            class="secondary"
            :aria-label="t('staff.board.next')"
            @click="start = shiftDay(start, days)"
          >
            →</button
          ><strong>{{ period }}</strong>
        </div>
        <div class="board-controls">
          <label
            ><span class="sr-only">{{ t("staff.arrival") }}</span
            ><input
              :value="start"
              type="date"
              required
              @change="start = $event.target.value || today" /></label
          ><select v-model.number="days" :aria-label="t('staff.board.range')">
            <option v-for="n in [7, 14, 30]" :key="n" :value="n">
              {{ t("staff.board.days", { n }) }}
            </option></select
          ><button
            class="text-button"
            :disabled="busy"
            @click="emit('refresh')"
          >
            {{ t("staff.refresh") }}
          </button>
        </div>
      </div>
      <div class="board-filters">
        <input
          v-model="query"
          type="search"
          :placeholder="t('staff.board.search')"
          :aria-label="t('staff.board.search')"
        />
        <div class="board-legend" :aria-label="t('staff.recordStatus')">
          <button :aria-pressed="state === 'all'" @click="state = 'all'">
            {{ t("staff.allStatuses") }}</button
          ><button
            v-for="key in states"
            :key="key"
            :aria-pressed="state === key"
            @click="state = state === key ? 'all' : key"
          >
            <i :class="key"></i>{{ t(`staff.board.${key}`) }}
          </button>
        </div>
      </div>
      <p class="board-hint">
        {{ t("staff.board.hint") }} · {{ resort?.timeZone || "Asia/Almaty" }}
      </p>
      <div
        class="board-scroll"
        tabindex="0"
        role="region"
        :aria-label="t('staff.board.title')"
      >
        <div class="board-grid" :style="{ '--days': days }">
          <div class="board-head">
            <div class="board-room-label">
              {{ t("staff.room")
              }}<small>{{ t("staff.board.roomType") }}</small>
            </div>
            <div
              v-for="day in dates"
              :key="day"
              :class="[
                'board-date',
                {
                  today: day === today,
                  weekend: [0, 6].includes(new Date(day).getUTCDay()),
                },
              ]"
            >
              <small>{{ fmt(day, { month: "short" }) }}</small
              ><strong>{{ fmt(day, { day: "numeric" }) }}</strong
              ><small>{{ fmt(day, { weekday: "short" }) }}</small>
            </div>
          </div>
          <div
            v-for="row in rows"
            :key="row.room.id"
            class="board-row"
            :style="{
              '--row-height': Math.max(74, row.lanes * 58 + 12) + 'px',
            }"
          >
            <div class="board-room-label">
              <strong>№ {{ row.room.number }}</strong
              ><small>{{ row.room.title }}</small
              ><span
                >{{ money(row.room.price) }} /
                {{ t("staff.board.night") }}</span
              ><small v-if="row.room.status !== 'active'" class="danger">{{
                t("staff.maintenance")
              }}</small>
            </div>
            <div class="board-track">
              <div class="board-cells">
                <button
                  v-for="day in dates"
                  :key="day"
                  :disabled="!available(row.room, day) || busy"
                  :class="{ today: day === today }"
                  :aria-label="
                    t('staff.board.createAt', {
                      room: row.room.number,
                      date: day,
                    })
                  "
                  @click="create(row.room, day)"
                >
                  <span aria-hidden="true">+</span>
                </button>
              </div>
              <button
                v-for="bar in row.bars"
                :key="bar.booking.id"
                :class="['stay-bar', bar.status]"
                :style="{
                  left: `calc(${bar.from} * var(--day-width) + 3px)`,
                  width: `calc(${bar.span} * var(--day-width) - 6px)`,
                  top: `${bar.lane * 58 + 7}px`,
                }"
                :title="label(bar.booking)"
                :aria-label="
                  t(`staff.board.${bar.status}`) + ': ' + label(bar.booking)
                "
                @click="emit('select', bar.booking)"
              >
                <strong>{{ bar.booking.guestLabel }}</strong
                ><small
                  >{{ t(`staff.board.${bar.status}`) }} ·
                  {{
                    money(bar.booking.paymentTerms?.total ?? bar.booking.total)
                  }}</small
                ><span
                  v-if="bar.status === 'reserved' && bar.booking.start < today"
                  class="stay-alert"
                  >{{ t("staff.board.notArrived") }}</span
                >
              </button>
            </div>
          </div>
        </div>
      </div>
      <div v-if="!rows.length" class="work-empty">
        <h3>{{ t("staff.noResults") }}</h3>
        <p>{{ t("staff.board.empty") }}</p>
        <button
          v-if="query || state !== 'all'"
          class="secondary"
          @click="
            query = '';
            state = 'all';
          "
        >
          {{ t("staff.resetFilters") }}
        </button>
      </div>
      <footer class="board-footer">
        <span>{{ t("staff.board.colorHint") }}</span
        ><span>{{ t("staff.board.exclusiveEnd") }}</span>
      </footer>
    </div>
  </section>
</template>
<style src="./occupancy.css"></style>
