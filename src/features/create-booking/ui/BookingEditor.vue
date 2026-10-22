<script setup>
import { reactive, computed, watch } from "vue";
import { Modal } from "@/shared/ui";
import { useBookingStore, dateAfter, nightsBetween } from "@/entities/booking";
import { ref } from "vue";
import { money } from "@/shared/lib";
const props = defineProps({
  resort: Object,
  rooms: Array,
  tariffs: Array,
  preset: Object,
  staff: Boolean,
});
const emit = defineEmits(["close", "saved"]);
const form = reactive({
  roomId: props.rooms.find((r) => r.status === "active")?.id || "",
  tariffId: props.tariffs.find((t) => t.status === "active")?.id || "",
  start: dateAfter(7),
  end: dateAfter(10),
  guests: 2,
  guestLabel: "",
  ...props.preset,
});
const room = computed(() => props.rooms.find((r) => r.id === form.roomId));
const tariff = computed(() =>
  props.tariffs.find((t) => t.id === form.tariffId),
);
const total = computed(() =>
  room.value && tariff.value
    ? Math.max(0, nightsBetween(form.start, form.end)) *
      (room.value.price + tariff.value.supplement * form.guests)
    : 0,
);
const store = useBookingStore(),
  busy = ref(false),
  error = ref(""),
  consent = ref(false);
async function save() {
  busy.value = true;
  error.value = "";
  try {
    const result = await store.create(form, props.staff);
    emit("saved", result);
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
watch(
  () => form.roomId,
  () => {
    if (room.value && form.guests > room.value.capacity)
      form.guests = room.value.capacity;
  },
);
</script>
<template>
  <Modal
    :title="staff ? 'Добавить бронирование' : 'Ваш отдых в ' + resort.name"
    :busy="busy"
    @close="emit('close')"
    ><form class="editor-form" @submit.prevent="save">
      <div class="booking-property">
        <img src="/assets/room.jpg" alt="Иллюстрация номера" />
        <div>
          <h3>{{ resort.name }}</h3>
          <p>{{ resort.city }}</p>
        </div>
      </div>
      <label v-if="staff"
        >Обозначение гостя<input
          v-model="form.guestLabel"
          required
          maxlength="80"
          placeholder="Например, Демо-гость 01"
      /></label>
      <p v-if="staff" class="field-help">
        Используйте вымышленные данные для проверки.
      </p>
      <div class="form-grid">
        <label
          >Заезд<input
            v-model="form.start"
            type="date"
            :min="dateAfter()"
            required /></label
        ><label
          >Выезд<input
            v-model="form.end"
            type="date"
            :min="form.start"
            required /></label
        ><label
          >Номер<select v-model="form.roomId" required>
            <option disabled value="">Нет активных номеров</option>
            <option
              v-for="r in rooms.filter((r) => r.status === 'active')"
              :key="r.id"
              :value="r.id"
            >
              № {{ r.number }} · {{ r.title }}
            </option>
          </select></label
        ><label
          >Гости<input
            v-model.number="form.guests"
            type="number"
            min="1"
            :max="room?.capacity || 4"
            required
        /></label>
      </div>
      <label
        >Тариф<select v-model="form.tariffId" required>
          <option disabled value="">Нет активных тарифов</option>
          <option
            v-for="t in tariffs.filter((t) => t.status === 'active')"
            :key="t.id"
            :value="t.id"
          >
            {{ t.name }} · +{{ money(t.supplement) }} / гость / ночь
          </option>
        </select></label
      >
      <div class="quote">
        <div>
          <span
            >Итого за
            {{ Math.max(0, nightsBetween(form.start, form.end)) || 0 }}
            ночи</span
          ><small>Номер + тариф для {{ form.guests }} гостей</small>
        </div>
        <strong>{{ money(total) }}</strong>
      </div>
      <label class="consent"
        ><input v-model="consent" type="checkbox" required /> Это
        демо-бронирование без оплаты</label
      >
      <p v-if="error" role="alert" class="form-error">{{ error }}</p>
      <div class="form-actions">
        <button
          type="button"
          class="secondary"
          :disabled="busy"
          @click="emit('close')"
        >
          Отмена</button
        ><button class="primary" :disabled="busy || !room || !tariff">
          {{ busy ? "Сохраняем…" : "Создать демо-бронь" }}
        </button>
      </div>
    </form></Modal
  >
</template>
