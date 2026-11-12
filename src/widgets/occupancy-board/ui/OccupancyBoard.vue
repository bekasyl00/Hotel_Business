<script setup>
import { computed, ref, watch, onMounted, onBeforeUnmount } from "vue";
import { useI18n } from "vue-i18n";
import {
  shiftDay,
  propertyToday,
  occupancyState,
  calendarRoomGroups,
  nightsBetween,
} from "@/entities/booking";
import { money } from "@/shared/lib";
const props = defineProps({
  rooms: Array,
  bookings: Array,
  resort: Object,
  busy: Boolean,
  readOnly: Boolean,
});
const emit = defineEmits(["select", "create", "refresh", "window"]);
const { t, locale } = useI18n();
const now = ref(Date.now());
const today = computed(() =>
  propertyToday(props.resort?.timeZone, new Date(now.value)),
);
const isMobile =
  typeof window !== "undefined" && window.innerWidth < 760;
const start = ref(shiftDay(today.value, isMobile ? -3 : -14)),
  days = ref(isMobile ? 14 : 60),
  endInput = computed(() => shiftDay(start.value, days.value - 1)),
  query = ref(""),
  state = ref("all"),
  collapsed = ref({});
const states = ["past", "active", "reserved", "pending"];
const dates = computed(() =>
  Array.from({ length: days.value }, (_, i) => shiftDay(start.value, i)),
);
const groups = computed(() =>
  calendarRoomGroups(props.rooms, props.bookings, start.value, days.value, {
    query: query.value,
    state: state.value,
    now: now.value,
  }),
);
const totalActivePlaces = computed(() =>
  groups.value.reduce((sum, g) => sum + g.places.length, 0),
);
const dateFormatters = computed(() => {
  const loc = locale.value;
  return {
    month: new Intl.DateTimeFormat(loc, { timeZone: "UTC", month: "short" }),
    day: new Intl.DateTimeFormat(loc, { timeZone: "UTC", day: "numeric" }),
    weekday: new Intl.DateTimeFormat(loc, {
      timeZone: "UTC",
      weekday: "short",
    }),
    periodStart: new Intl.DateTimeFormat(loc, {
      timeZone: "UTC",
      day: "numeric",
      month: "long",
    }),
    periodEnd: new Intl.DateTimeFormat(loc, {
      timeZone: "UTC",
      day: "numeric",
      month: "long",
      year: "numeric",
    }),
  };
});
const dayHeaders = computed(() => {
  const f = dateFormatters.value;
  return dates.value.map((day) => {
    const dt = new Date(`${day}T00:00:00Z`);
    const weekdayNum = dt.getUTCDay();
    return {
      day,
      isToday: day === today.value,
      isWeekend: weekdayNum === 0 || weekdayNum === 6,
      month: f.month.format(dt),
      dayNum: f.day.format(dt),
      weekday: f.weekday.format(dt),
    };
  });
});
const period = computed(() => {
  const f = dateFormatters.value;
  const end = shiftDay(start.value, days.value - 1);
  return `${f.periodStart.format(new Date(`${start.value}T00:00:00Z`))} — ${f.periodEnd.format(new Date(`${end}T00:00:00Z`))}`;
});
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
const blockedPlaceDays = computed(() => {
  const result = new Map();
  for (const group of groups.value) {
    for (const row of group.rows) {
      const set = new Set();
      for (const bar of row.bars) {
        if (!["pending", "confirmed"].includes(bar.booking.status)) continue;
        for (const day of dates.value) {
          if (bar.booking.start <= day && day < bar.booking.end) set.add(day);
        }
      }
      result.set(row.place.id, set);
    }
  }
  return result;
});
function available(room, place, day) {
  return (
    !props.readOnly &&
    room.status === "active" &&
    (!place || place.status === "active") &&
    props.resort?.status === "published" &&
    day >= today.value &&
    !(place && blockedPlaceDays.value.get(place.id)?.has(day))
  );
}
function create(room, day, place = null) {
  emit("create", {
    roomId: room.id,
    start: day,
    end: shiftDay(day, 1),
    guests: place ? 1 : Math.min(2, room.capacity),
    ...(place ? { placeIds: [place.id] } : {}),
  });
}
function toggleRoom(roomId) {
  collapsed.value = {
    ...collapsed.value,
    [roomId]: !collapsed.value[roomId],
  };
}
function setEndDate(nextEnd) {
  if (!nextEnd || nextEnd < start.value) return;
  const span = nightsBetween(start.value, nextEnd) + 1;
  days.value = Math.max(1, Math.min(120, span));
}
function goToday() {
  start.value =
    days.value === 60
      ? shiftDay(today.value, -14)
      : shiftDay(today.value, -Math.min(14, Math.floor(days.value / 4)));
}
watch(
  [start, days],
  () => {
    emit("window", {
      start: start.value,
      end: shiftDay(start.value, days.value),
    });
  },
  { immediate: true },
);
const label = (b) =>
  `${b.guestLabel} · № ${b.unit}${b.placeLabels?.length ? ` (${b.placeLabels.join(", ")})` : ""} · ${b.start} — ${b.end} · ${money(b.paymentTerms?.total ?? b.total)}`;
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
          key === "roomsCount"
            ? `${resort?.name || ""} · ${t("staff.board.placesCount", { count: totalActivePlaces })}`
            : t("staff.board.today")
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
          ><button class="secondary" @click="goToday">
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
            ><span class="sr-only">{{ t("staff.board.fromDate") }}</span
            ><input
              :value="start"
              type="date"
              required
              @change="start = $event.target.value || today" /></label
          ><label
            ><span class="sr-only">{{ t("staff.board.toDate") }}</span
            ><input
              :value="endInput"
              type="date"
              :min="start"
              :max="shiftDay(start, 119)"
              required
              @change="setEndDate($event.target.value)" /></label
          ><select v-model.number="days" :aria-label="t('staff.board.range')">
            <option
              v-for="n in [7, 14, 30, 60, 90].includes(days)
                ? [7, 14, 30, 60, 90]
                : [7, 14, 30, 60, 90, days]"
              :key="n"
              :value="n"
            >
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
      <p class="board-hint">{{ t("staff.board.hint") }}</p>
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
              }}<small
                >{{ t("staff.board.places") }} ·
                {{ t("staff.board.roomType") }}</small
              >
            </div>
            <div
              v-for="h in dayHeaders"
              :key="h.day"
              :class="[
                'board-date',
                {
                  today: h.isToday,
                  weekend: h.isWeekend,
                },
              ]"
            >
              <small>{{ h.month }}</small
              ><strong>{{ h.dayNum }}</strong
              ><small>{{ h.weekday }}</small>
            </div>
          </div>
          <template v-for="group in groups" :key="group.room.id">
            <div class="board-group-header">
              <div class="board-room-label board-room-group-label">
                <div class="room-group-top">
                  <strong>№ {{ group.room.number }}</strong>
                  <button
                    type="button"
                    class="room-collapse-toggle"
                    :aria-expanded="!collapsed[group.room.id]"
                    :aria-label="
                      t(
                        collapsed[group.room.id]
                          ? 'staff.board.expandRoom'
                          : 'staff.board.collapseRoom',
                        { room: group.room.number },
                      )
                    "
                    @click="toggleRoom(group.room.id)"
                  >
                    {{ collapsed[group.room.id] ? "▸" : "▾" }}
                  </button>
                </div>
                <small
                  >{{ group.room.title }} ·
                  {{
                    t("staff.board.placesCount", {
                      count: group.places.length,
                    })
                  }}</small
                ><span
                  >{{ money(group.room.price) }} /
                  {{ t("staff.board.night") }}</span
                ><small
                  v-if="group.room.status !== 'active'"
                  class="danger"
                  >{{ t("staff.maintenance") }}</small
                >
              </div>
              <div class="board-track board-group-track">
                <div class="board-cells">
                  <span
                    v-for="day in dates"
                    :key="day"
                    :class="['board-group-cell', { today: day === today }]"
                  ></span>
                </div>
              </div>
            </div>
            <template v-if="!collapsed[group.room.id]">
              <div
                v-for="row in group.rows"
                :key="row.place.id"
                class="board-row board-place-row"
                :style="{
                  '--row-height': Math.max(58, row.lanes * 54 + 10) + 'px',
                }"
              >
                <div class="board-room-label board-place-label">
                  <strong>{{ row.place.unitLabel }}</strong>
                  <small
                    >{{ t("staff.board.place") }}
                    {{ row.place.label.toUpperCase() }}</small
                  >
                </div>
                <div class="board-track">
                  <div class="board-cells">
                    <button
                      v-for="day in dates"
                      :key="day"
                      :disabled="!available(group.room, row.place, day) || busy"
                      :class="{ today: day === today }"
                      :aria-label="`${row.place.unitLabel} · ${day}`"
                      @click="create(group.room, day, row.place)"
                    >
                      <span aria-hidden="true">+</span>
                    </button>
                  </div>
                  <button
                    v-for="bar in row.bars"
                    :key="`${bar.booking.id}-${row.place.id}`"
                    :class="['stay-bar', bar.status]"
                    :style="{
                      left: `calc(${bar.from} * var(--day-width) + 3px)`,
                      width: `calc(${bar.span} * var(--day-width) - 6px)`,
                      top: `${bar.lane * 54 + 5}px`,
                    }"
                    :title="label(bar.booking)"
                    :aria-label="
                      t(`staff.board.${bar.status}`) + ': ' + label(bar.booking)
                    "
                    @click="emit('select', bar.booking)"
                  >
                    <strong>{{ bar.booking.guestLabel }}</strong
                    ><small
                      >{{ t(`staff.board.${bar.status}`)
                      }}<template v-if="(bar.booking.placesCount || bar.booking.guests) > 1">
                        · {{ row.place.unitLabel }} ({{
                          bar.booking.placesCount || bar.booking.guests
                        }})</template
                      >
                      ·
                      {{
                        money(
                          bar.booking.paymentTerms?.total ?? bar.booking.total,
                        )
                      }}</small
                    ><span
                      v-if="
                        bar.status === 'reserved' && bar.booking.start < today
                      "
                      class="stay-alert"
                      >{{ t("staff.board.notArrived") }}</span
                    >
                  </button>
                </div>
              </div>
            </template>
          </template>
        </div>
      </div>
      <div v-if="!groups.length" class="work-empty">
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
