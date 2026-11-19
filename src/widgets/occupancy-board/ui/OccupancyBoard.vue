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
const allGroups = computed(() =>
  calendarRoomGroups(props.rooms, props.bookings, start.value, days.value, { now: now.value }),
);
const groups = computed(() => query.value.trim() || state.value !== "all"
  ? calendarRoomGroups(props.rooms, props.bookings, start.value, days.value, {
      query: query.value, state: state.value, now: now.value,
    })
  : allGroups.value);
const scrollArea = ref(null);
const scrollTop = ref(0);
const viewportHeight = ref(640);
const touch = ref(false);
const laneHeight = computed(() => touch.value ? 32 : 24);
const groupHeight = computed(() => touch.value ? 34 : 26);
// Offsets account for collapsed rooms and bookings which share a legacy place lane.
const layout = computed(() => {
  const rows = [];
  let height = 0;
  for (const group of groups.value) {
    rows.push({ key: "room-" + group.room.id, group, top: height, height: groupHeight.value });
    height += groupHeight.value;
    if (collapsed.value[group.room.id]) continue;
    for (const row of group.rows) {
      const size = row.lanes * laneHeight.value;
      rows.push({ key: "place-" + row.place.id, group, row, top: height, height: size });
      height += size;
    }
  }
  return { rows, height };
});
const visibleRows = computed(() => {
  const { rows, height } = layout.value;
  const top = Math.min(scrollTop.value, Math.max(0, height - viewportHeight.value));
  const margin = 6 * laneHeight.value;
  const first = Math.max(0, top - margin);
  const last = top + viewportHeight.value + margin + 48;
  return rows.filter(item => item.top + item.height > first && item.top < last);
});
function updateWindow() {
  if (!scrollArea.value) return;
  scrollTop.value = scrollArea.value.scrollTop;
  viewportHeight.value = scrollArea.value.clientHeight;
}
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
const monthBands = computed(() => {
  const bands = [];
  for (const date of dayHeaders.value) {
    const key = date.day.slice(0, 7);
    const last = bands.at(-1);
    if (last?.key === key) last.span++;
    else bands.push({ key, label: date.month, span: 1 });
  }
  return bands;
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
  for (const group of allGroups.value) {
    for (const row of group.rows) {
      const set = new Set();
      for (const bar of row.bars) {
        if (!["pending", "confirmed"].includes(bar.booking.status)) continue;
        for (let i = bar.from; i < bar.from + bar.span; i++) set.add(dates.value[i]);
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
let timer, resize, pointer;
function updatePointer() { touch.value = pointer.matches; }
onMounted(() => {
  pointer = window.matchMedia("(pointer: coarse)");
  updatePointer();
  pointer.addEventListener("change", updatePointer);
  resize = new ResizeObserver(updateWindow);
  resize.observe(scrollArea.value);
  updateWindow();
  timer = setInterval(() => {
    now.value = Date.now();
  }, 30000);
});
onBeforeUnmount(() => {
  clearInterval(timer);
  resize?.disconnect();
  pointer?.removeEventListener("change", updatePointer);
});
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
        ref="scrollArea"
        class="board-scroll"
        tabindex="0"
        role="region"
        :aria-label="t('staff.board.title')"
        @scroll.passive="updateWindow"
      >
        <div class="board-grid" :style="{ '--days': days, '--lane-height': laneHeight + 'px' }">
          <div class="board-head">
            <div class="board-room-label">{{ t("staff.room") }} / {{ t("staff.board.place") }}</div>
            <div>
              <div class="board-months">
                <span v-for="band in monthBands" :key="band.key"
                  :style="{ width: 'calc(' + band.span + ' * var(--day-width))' }">{{ band.label }}</span>
              </div>
              <div class="board-days">
                <div v-for="h in dayHeaders" :key="h.day" class="board-date"
                  :class="{ today: h.isToday, weekend: h.isWeekend }" :title="h.day">
                  <strong>{{ h.dayNum }}</strong><small>{{ h.weekday }}</small>
                </div>
              </div>
            </div>
          </div>
          <div :style="{ height: layout.height + 'px' }">
            <div :style="{ paddingTop: (visibleRows[0]?.top || 0) + 'px' }">
              <div v-for="item in visibleRows" :key="item.key"
                :class="item.row ? 'board-row' : 'board-group-header'"
                :style="{ height: item.height + 'px' }">
                <template v-if="!item.row">
                  <button type="button" class="board-room-label board-room-toggle"
                    :aria-expanded="!collapsed[item.group.room.id]"
                    :aria-label="t(collapsed[item.group.room.id] ? 'staff.board.expandRoom' : 'staff.board.collapseRoom', { room: item.group.room.number })"
                    :title="[item.group.room.title, t('staff.board.placesCount', { count: item.group.rows.length }), money(item.group.room.price) + ' / ' + t('staff.board.night')].join(' · ')"
                    @click="toggleRoom(item.group.room.id)">
                    <span aria-hidden="true">{{ collapsed[item.group.room.id] ? '▸' : '▾' }}</span>
                    <strong>№ {{ item.group.room.number }}</strong>
                    <small>{{ item.group.room.status === 'maintenance' ? t('staff.maintenance') : item.group.room.title }}</small>
                  </button>
                  <div class="board-group-track" aria-hidden="true"></div>
                </template>
                <template v-else>
                  <div class="board-room-label board-place-label"><strong>{{ item.row.place.unitLabel }}</strong></div>
                  <div class="board-track">
                    <div class="board-cells">
                      <button v-for="day in dates" :key="day" type="button"
                        :disabled="!available(item.group.room, item.row.place, day) || busy"
                        :class="{ today: day === today }"
                        :aria-label="item.row.place.unitLabel + ' · ' + day"
                        @click="create(item.group.room, day, item.row.place)"><span aria-hidden="true">+</span></button>
                    </div>
                    <button v-for="bar in item.row.bars" :key="bar.booking.id" type="button"
                      :class="['stay-bar', bar.status]"
                      :style="{
                        left: 'calc(' + bar.from + ' * var(--day-width) + 1px)',
                        width: 'calc(' + bar.span + ' * var(--day-width) - 2px)',
                        top: (bar.lane * laneHeight + 1) + 'px',
                      }"
                      :title="t(`staff.board.${bar.status}`) + ' · ' + label(bar.booking)"
                      :aria-label="t(`staff.board.${bar.status}`) + ' · ' + label(bar.booking)"
                      @click="emit('select', bar.booking)">
                      <span v-if="bar.status === 'reserved' && bar.booking.start < today"
                        :title="t('staff.board.notArrived')">!</span>
                      <strong>{{ bar.booking.guestLabel }}</strong>
                    </button>
                  </div>
                </template>
              </div>
            </div>
          </div>
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
