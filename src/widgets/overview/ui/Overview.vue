<script setup>
import { computed } from "vue";
import { money, dateLabel } from "@/shared/lib";
import { dateAfter } from "@/entities/booking";
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
  <div class="metrics">
    <article>
      <span>Санатории</span
      ><strong>{{
        resorts.filter((r) => r.status !== "archived").length
      }}</strong
      ><small
        >{{
          resorts.filter((r) => r.status === "published").length
        }}
        опубликовано</small
      >
    </article>
    <article>
      <span>Номерной фонд</span
      ><strong>{{ rooms.length }} <small>комнат</small></strong
      ><small
        >{{ rooms.filter((r) => r.status === "maintenance").length }} на
        обслуживании</small
      >
    </article>
    <article>
      <span>Заселено сегодня</span><strong>{{ occupied }}</strong
      ><small
        >из {{ rooms.filter((r) => r.status === "active").length }} активных
        номеров</small
      >
    </article>
    <article>
      <span>Сумма активных броней</span
      ><strong class="metric-money">{{ money(total) }}</strong
      ><small>Расчётная стоимость, не выручка</small>
    </article>
  </div>
  <section class="surface">
    <div class="surface-heading">
      <div>
        <h2>Ближайшие заезды</h2>
        <p>Подтверждённые бронирования с сегодняшнего дня</p>
      </div>
      <button class="text-button" @click="emit('bookings')">
        Все бронирования →
      </button>
    </div>
    <div
      v-if="upcoming.length"
      class="table-scroll"
      tabindex="0"
      role="region"
      aria-label="Таблица данных"
    >
      <table>
        <thead>
          <tr>
            <th>Гость / бронь</th>
            <th>Санаторий</th>
            <th>Даты</th>
            <th>Сумма</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in upcoming" :key="b.id">
            <td>
              <strong>{{ b.guestLabel }}</strong
              ><small>№ {{ b.id.slice(0, 8) }} · комната {{ b.unit }}</small>
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
      <h3>Ближайших заездов пока нет</h3>
      <p>Создайте первую бронь вручную или оформите её на сайте.</p>
      <button class="primary" @click="emit('create')">
        Добавить бронирование
      </button>
    </div>
  </section>
</template>
