<script setup>
import { useI18n } from "vue-i18n";
import { computed } from "vue";
import { money, dateLabel } from "@/shared/lib";
import { dateAfter } from "@/entities/booking";
const { t } = useI18n();
const props = defineProps({ resorts: Array, rooms: Array, bookings: Array });
const emit = defineEmits(["create", "bookings"]);
const today = dateAfter();
const active = computed(() =>
  props.bookings.filter((b) => b.status === "confirmed"),
);
const occupied = computed(
  () =>
    new Set(
      active.value
        .filter((b) => b.start <= today && b.end > today)
        .map((b) => b.roomId),
    ).size,
);
const upcoming = computed(() =>
  active.value
    .filter((b) => b.start >= today)
    .sort((a, b) => a.start.localeCompare(b.start))
    .slice(0, 5),
);
const total = computed(() => active.value.reduce((s, b) => s + b.total, 0));
</script>
<template>
  <section
    v-if="bookings.some((b) => b.status === 'pending')"
    class="surface surface-heading"
  >
    <div>
      <h2>
        {{ t("staff.pendingLabel") }}
        {{ bookings.filter((b) => b.status === "pending").length }}
      </h2>
      <p>{{ t("staff.checkNewRequests") }}</p>
    </div>
    <button class="primary" @click="emit('bookings')">
      {{ t("staff.openRequests") }}
    </button>
  </section>
  <div class="metrics">
    <article>
      <span>{{ t("staff.resorts") }}</span
      ><strong>{{
        resorts.filter((r) => r.status !== "archived").length
      }}</strong
      ><small
        >{{ resorts.filter((r) => r.status === "published").length }}
        {{ t("staff.publishedCountSuffix") }}</small
      >
    </article>
    <article>
      <span>{{ t("staff.inventory") }}</span
      ><strong
        >{{ rooms.length }}
        <small>{{ t("staff.roomsCountSuffix") }}</small></strong
      ><small
        >{{ rooms.filter((r) => r.status === "maintenance").length }}
        {{ t("staff.maintenanceCountSuffix") }}</small
      >
    </article>
    <article>
      <span>{{ t("staff.occupiedToday") }}</span
      ><strong>{{ occupied }}</strong
      ><small>{{
        t("staff.activeRoomsCount", {
          count: rooms.filter((r) => r.status === "active").length,
        })
      }}</small>
    </article>
    <article>
      <span>{{ t("staff.activeBookingAmount") }}</span
      ><strong class="metric-money">{{ money(total) }}</strong
      ><small>{{ t("staff.estimatedNotRevenue") }}</small>
    </article>
  </div>
  <section class="surface">
    <div class="surface-heading">
      <div>
        <h2>{{ t("staff.upcomingArrivals") }}</h2>
        <p>{{ t("staff.upcomingSubtitle") }}</p>
      </div>
      <button class="text-button" @click="emit('bookings')">
        {{ t("staff.allBookings") }}
      </button>
    </div>
    <div
      v-if="upcoming.length"
      class="table-scroll"
      tabindex="0"
      role="region"
      :aria-label="t('staff.dataTable')"
    >
      <table>
        <thead>
          <tr>
            <th>{{ t("staff.guestBooking") }}</th>
            <th>{{ t("staff.resort") }}</th>
            <th>{{ t("staff.dates") }}</th>
            <th>{{ t("staff.amount") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in upcoming" :key="b.id">
            <td>
              <strong>{{ b.guestLabel }}</strong
              ><small>{{
                t("staff.bookingRoom", { id: b.id.slice(0, 8), room: b.unit })
              }}</small>
            </td>
            <td>{{ b.resortName }}</td>
            <td>{{ dateLabel(b.start) }} → {{ dateLabel(b.end) }}</td>
            <td>{{ money(b.total) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="work-empty">
      <span>▤</span>
      <h3>{{ t("staff.noArrivals") }}</h3>
      <p>{{ t("staff.firstBookingHint") }}</p>
      <button class="primary" @click="emit('create')">
        {{ t("staff.addBooking") }}
      </button>
    </div>
  </section>
</template>
