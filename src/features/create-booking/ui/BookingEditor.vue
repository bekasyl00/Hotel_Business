<script setup>
import { useI18n } from "vue-i18n";
const { t } = useI18n();
import { isDemo, isMobile, isStaffApp } from "@/shared/config";
import { reactive, computed, watch } from "vue";
import { Modal } from "@/shared/ui";
import { useBookingStore, dateAfter, nightsBetween } from "@/entities/booking";
import { ref } from "vue";
import { useGuestAccountStore } from "@/entities/guest-account";
const guestAccount = useGuestAccountStore();
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
  guestPhone: "",
  ...props.preset,
});
const room = computed(() => props.rooms.find((r) => r.id === form.roomId));
const tariff = computed(() =>
  props.tariffs.find((t) => t.id === form.tariffId),
);
const total = computed(() =>
  room.value && tariff.value
    ? Math.max(0, nightsBetween(form.start, form.end)) *
      Math.round(
        ((room.value.price + tariff.value.supplement * form.guests) *
          (100 -
            (tariff.value.priceKind === "discount"
              ? tariff.value.discountPercent
              : 0))) /
          100,
      )
    : 0,
);
const store = useBookingStore(),
  busy = ref(false),
  error = ref(""),
  consent = ref(false);
let attempt = null;
async function save() {
  busy.value = true;
  error.value = "";
  try {
    const fingerprint = JSON.stringify(form);
    if (attempt?.fingerprint !== fingerprint)
      attempt = { fingerprint, id: crypto.randomUUID() };
    const result = await store.create(
      { ...form, requestId: attempt.id },
      props.staff,
    );
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
    :title="
      staff
        ? t('public.addBooking')
        : t('public.yourStayAt') + ' ' + resort.name
    "
    :busy="busy"
    @close="emit('close')"
    ><form class="editor-form" @submit.prevent="save">
      <div class="booking-property">
        <img
          :src="
            room?.media?.find((m) => m.kind === 'image')?.url ||
            '/assets/room.jpg'
          "
          :alt="
            room?.media?.find((m) => m.kind === 'image')?.alt ||
            t('public.illustrativeRoomImage')
          "
        />
        <div>
          <h3>{{ resort.name }}</h3>
          <p>{{ resort.city }}</p>
        </div>
      </div>
      <label v-if="staff || !isDemo"
        >{{ t("public.guestName")
        }}<input
          v-model="form.guestLabel"
          required
          maxlength="80"
          :placeholder="t('public.forExampleDemoGuest01')"
      /></label>
      <label v-if="!isDemo"
        >{{ t("public.contactPhone")
        }}<input
          v-model="form.guestPhone"
          type="tel"
          :required="!staff"
          maxlength="30"
          placeholder="+7 …"
      /></label>
      <p v-if="staff && isDemo" class="field-help">
        {{ t("public.useFictionalDetailsForTesting") }}
      </p>
      <RouterLink
        v-if="isMobile && !isStaffApp && !isDemo && !guestAccount.authenticated"
        to="/account/login"
        class="field-help"
        >{{ t("common.mobile.bookingLogin") }}</RouterLink
      >
      <div class="form-grid">
        <label
          >{{ t("public.checkin")
          }}<input
            v-model="form.start"
            type="date"
            :min="dateAfter()"
            required /></label
        ><label
          >{{ t("public.checkout")
          }}<input
            v-model="form.end"
            type="date"
            :min="form.start"
            required /></label
        ><label
          >{{ t("public.roomInReceiptPage")
          }}<select v-model="form.roomId" required>
            <option disabled value="">{{ t("public.noActiveRooms") }}</option>
            <option
              v-for="r in rooms.filter((r) => r.status === 'active')"
              :key="r.id"
              :value="r.id"
            >
              № {{ r.number }} · {{ r.title }}
            </option>
          </select></label
        ><label
          >{{ t("public.guests")
          }}<input
            v-model.number="form.guests"
            type="number"
            min="1"
            :max="room?.capacity || 4"
            required
        /></label>
      </div>
      <label
        >{{ t("public.rate")
        }}<select v-model="form.tariffId" required>
          <option disabled value="">{{ t("public.noActiveRates") }}</option>
          <option
            v-for="offer in tariffs.filter(
              (offer) => offer.status === 'active',
            )"
            :key="offer.id"
            :value="offer.id"
          >
            {{ offer.name
            }}{{
              offer.priceKind === "discount"
                ? t("public.discountInBookingEditor", [offer.discountPercent])
                : ""
            }}
            · +{{ money(offer.supplement) }} {{ t("public.guestNight") }}
          </option>
        </select></label
      >
      <div class="quote">
        <div>
          <span
            >{{ t("public.totalFor") }}
            {{ Math.max(0, nightsBetween(form.start, form.end)) || 0 }}
            {{ t("public.nightsInBookingEditor") }}</span
          ><small
            >{{ t("public.roomAndRateFor") }} {{ form.guests }}
            {{ t("public.guestsInBookingEditor") }}</small
          >
        </div>
        <strong>{{ money(total) }}</strong>
      </div>
      <p class="field-help">
        {{ t("public.checkinFrom") }} {{ resort.checkInTime || "14:00" }} ·
        {{ resort.timeZone || "Asia/Almaty"
        }}{{ t("public.refunds100At48HoursOrMore70At2448HoursNone") }}
      </p>
      <label class="consent"
        ><input v-model="consent" type="checkbox" required />
        {{
          isDemo
            ? t("public.thisIsADemoBookingWithNoRealCharge")
            : t(
                "public.sendTheRequestToTheManagerTheBookingRequiresConfirmationNothingIs",
              )
        }}</label
      >
      <p v-if="error" role="alert" class="form-error">{{ error }}</p>
      <div class="form-actions">
        <button
          type="button"
          class="secondary"
          :disabled="busy"
          @click="emit('close')"
        >
          {{ t("public.cancel") }}</button
        ><button class="primary" :disabled="busy || !room || !tariff">
          {{
            busy
              ? t("public.saving")
              : isDemo
                ? t("public.createDemoRequest")
                : t("public.sendRequest")
          }}
        </button>
      </div>
    </form></Modal
  >
</template>
