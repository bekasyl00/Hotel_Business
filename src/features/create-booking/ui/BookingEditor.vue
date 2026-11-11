<script setup>
import {
  childDatePreview,
  childBirthFromIin,
  partySize,
  roomForParty,
} from "../model/children.js";
import { useI18n } from "vue-i18n";
const { t } = useI18n();
import { isDemo } from "@/shared/config";
import { reactive, computed, watch, onMounted, useId } from "vue";
import { Modal } from "@/shared/ui";
import {
  useBookingStore,
  propertyToday,
  shiftDay,
  nightsBetween,
  quoteStay,
  validateChildren,
  paymentTerms,
  customerQuote,
} from "@/entities/booking";
import { ref } from "vue";
import { useGuestAccountStore } from "@/entities/guest-account";
const guestAccount = useGuestAccountStore();
import { money, dateLabel } from "@/shared/lib";
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
  ...(props.staff
    ? {}
    : { tariffId: props.tariffs.find((t) => t.status === "active")?.id || "" }),
  start: shiftDay(propertyToday(props.resort.timeZone), 7),
  end: shiftDay(propertyToday(props.resort.timeZone), 10),
  guests: 2,
  childrenAges: [],
  guestLabel: "",
  guestPhone: "",
  ...props.preset,
});
const room = computed(() => props.rooms.find((r) => r.id === form.roomId));
const tariff = computed(() =>
  props.tariffs.find((t) => t.id === form.tariffId),
);
const price = computed(() =>
  room.value &&
  (props.staff || tariff.value) &&
  !partyError.value &&
  !capacityError.value &&
  !validateChildren(form.guests, form.childrenAges)
    ? quoteStay(room.value, props.staff ? null : tariff.value, form)
    : null,
);
const total = computed(() => price.value?.total || 0);
const settlement = computed(() =>
  price.value ? paymentTerms(props.resort, total.value) : null,
);
const displayPrice = computed(() => customerQuote(props.resort, price.value));
const quotedTariffs = computed(() =>
  props.tariffs
    .filter((offer) => offer.status === "active")
    .map((offer) => ({
      ...offer,
      quote: room.value
        ? customerQuote(props.resort, quoteStay(room.value, offer, form))
        : null,
    })),
);
const children = ref([]);
const adults = ref(form.guests);
const childInputPrefix = useId();
let childSequence = 0;
const childPreviews = computed(() =>
  children.value.map((child) =>
    childDatePreview(
      child.iin,
      form.start,
      propertyToday(props.resort.timeZone),
    ),
  ),
);
const partyTotal = computed(() =>
  partySize(adults.value, children.value.length),
);
const partyError = computed(() =>
  partyTotal.value === null ? t("common.children.partyLimit") : "",
);
const canAddChild = computed(
  () => partyTotal.value !== null && partyTotal.value < 4,
);
watch(
  [partyTotal, childPreviews],
  () => {
    form.guests = partyTotal.value;
    form.childrenAges = childPreviews.value.map((child) =>
      child.status === "ready" ? child.age : null,
    );
  },
  { immediate: true, flush: "sync" },
);
onMounted(async () => {
  if (!props.staff) {
    try {
      await guestAccount.restore();
    } catch (e) {
      error.value = e.message;
    }
  }
});
const selectedRoomNotice = ref("");
const capacityError = computed(() =>
  room.value && Number(form.guests) > room.value.capacity
    ? t("common.children.roomCapacity", {
        capacity: room.value.capacity,
        guests: form.guests,
      })
    : "",
);
function fitRoom() {
  const larger = roomForParty(props.rooms, form.roomId, Number(form.guests));
  if (larger && larger.id !== form.roomId) {
    form.roomId = larger.id;
    selectedRoomNotice.value = t("common.children.roomChanged", {
      room: `${larger.number} · ${larger.title}`,
      capacity: larger.capacity,
    });
  }
}
function addChild() {
  if (!canAddChild.value) return;
  children.value.push({ id: ++childSequence, iin: "" });
  fitRoom();
}
function removeChild(id) {
  children.value = children.value.filter((child) => child.id !== id);
}
function ageDescription(child) {
  if (child.months === 0) return t("common.children.ageUnderMonth");
  return child.age < 1
    ? t("common.children.ageMonths", { months: child.months })
    : t("common.children.ageYears", { years: child.age });
}
function childError(index) {
  const child = childPreviews.value[index];
  return !child || ["empty", "incomplete", "ready"].includes(child.status)
    ? ""
    : t(`common.children.${child.status}`);
}
watch(() => form.guests, fitRoom);
const store = useBookingStore(),
  busy = ref(false),
  error = ref(""),
  consent = ref(false);
let attempt = null;
async function save() {
  error.value =
    partyError.value ||
    capacityError.value ||
    (!props.staff && !guestAccount.authenticated
      ? t("common.checkout.loginRequired")
      : children.value.some(
            (c) =>
              !childBirthFromIin(
                c.iin,
                form.start,
                propertyToday(props.resort.timeZone),
              ),
          )
        ? t("common.children.invalidIin")
        : validateChildren(form.guests, form.childrenAges));
  if (error.value) return;
  if (price.value && !settlement.value) {
    error.value = t("common.settlement.notConfigured");
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    const { guestLabel, guestPhone, ...publicForm } = form;
    const payload = {
      ...(props.staff ? form : publicForm),
      childrenBirthDates: children.value.map((c) =>
        childBirthFromIin(
          c.iin,
          form.start,
          propertyToday(props.resort.timeZone),
        ),
      ),
    };
    const fingerprint = JSON.stringify(payload);
    if (attempt?.fingerprint !== fingerprint)
      attempt = { fingerprint, id: crypto.randomUUID() };
    const result = await store.create(
      {
        ...payload,
        requestId: attempt.id,
      },
      props.staff,
    );
    emit("saved", result);
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <Modal
    :title="staff ? t('public.addBooking') : t('common.children.bookingTitle')"
    :busy="busy"
    @close="emit('close')"
    ><form class="editor-form booking-editor" @submit.prevent="save">
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
      <label v-if="staff"
        >{{ t("public.guestName")
        }}<input
          v-model="form.guestLabel"
          required
          maxlength="80"
          :placeholder="t('public.forExampleDemoGuest01')"
      /></label>
      <label v-if="staff && !isDemo"
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
      <p v-if="!staff" class="field-help">
        {{
          t("common.checkout.profileContact", {
            name: guestAccount.session?.profile?.name || "—",
            phone: guestAccount.session?.account?.phone || "—",
          })
        }}
      </p>
      <RouterLink
        v-if="!staff && !guestAccount.authenticated"
        to="/account/login"
        class="field-help"
        >{{ t("common.checkout.loginRequired") }}</RouterLink
      >
      <div class="form-grid">
        <label
          >{{ t("public.checkin")
          }}<input
            v-model="form.start"
            type="date"
            :min="propertyToday(props.resort.timeZone)"
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
              № {{ r.number }} · {{ r.title }} ·
              {{
                t("common.children.capacityOption", { capacity: r.capacity })
              }}
            </option>
          </select></label
        ><label
          >{{ t("common.children.olderGuests")
          }}<input
            v-model.number="adults"
            type="number"
            inputmode="numeric"
            min="1"
            :max="4 - children.length"
            required
        /></label>
      </div>
      <p v-if="selectedRoomNotice" class="field-help" role="status">
        {{ selectedRoomNotice }}
      </p>
      <p v-if="room" class="field-help" role="status">
        {{
          t("public.calendar.bookedPlaces", {
            guests: form.guests,
            capacity: room.capacity,
          })
        }}<template v-if="room.capacity > 1 && form.guests < room.capacity">
          · {{ t("public.calendar.sharedRoomNotice") }}</template
        >
      </p>
      <div v-if="capacityError" class="form-error" role="alert">
        <p>{{ capacityError }}</p>
        <RouterLink
          v-if="!staff"
          :to="{
            path: `/resorts/${resort.id}`,
            query: { start: form.start, end: form.end, guests: form.guests },
          }"
          @click="emit('close')"
          >{{ t("common.children.findRoom") }}</RouterLink
        >
      </div>
      <section
        class="party-section"
        :aria-label="t('common.children.partyTitle')"
      >
        <div class="party-heading">
          <div>
            <h3>{{ t("common.children.partyTitle") }}</h3>
            <p class="field-help">{{ t("common.children.youngerGuests") }}</p>
          </div>
          <span class="party-total" role="status">{{
            t("common.children.total", { count: partyTotal ?? "—" })
          }}</span>
        </div>
        <p v-if="partyError" class="form-error" role="alert">
          {{ partyError }}
        </p>
        <div
          v-for="(child, index) in children"
          :key="child.id"
          class="child-entry"
        >
          <div class="child-heading">
            <label :for="`${childInputPrefix}-${child.id}`">{{
              t("common.children.iin", { number: index + 1 })
            }}</label>
            <button
              type="button"
              class="child-remove"
              :aria-label="
                t('common.children.removeNumber', { number: index + 1 })
              "
              :disabled="busy"
              @click="removeChild(child.id)"
            >
              ×
            </button>
          </div>
          <input
            :id="`${childInputPrefix}-${child.id}`"
            v-model="child.iin"
            type="text"
            inputmode="numeric"
            minlength="12"
            maxlength="12"
            pattern="[0-9]{12}"
            autocomplete="off"
            autocapitalize="none"
            :spellcheck="false"
            :aria-invalid="!!childError(index)"
            :aria-describedby="`${childInputPrefix}-${child.id}-result`"
            :disabled="busy"
            required
          />
          <div
            :id="`${childInputPrefix}-${child.id}-result`"
            aria-live="polite"
          >
            <p v-if="childPreviews[index]?.birth" class="child-age">
              <span>{{ dateLabel(childPreviews[index].birth) }}</span>
              <strong>{{ ageDescription(childPreviews[index]) }}</strong>
            </p>
            <p v-if="childError(index)" class="form-error">
              {{ childError(index) }}
            </p>
            <p
              v-else-if="childPreviews[index]?.status === 'incomplete'"
              class="field-help"
            >
              {{ t("common.children.completeIin") }}
            </p>
          </div>
        </div>
        <button
          type="button"
          class="add-child"
          :disabled="busy || !canAddChild"
          @click="addChild"
        >
          <span aria-hidden="true">＋</span>{{ t("common.children.add") }}
        </button>
        <p v-if="partyTotal === 4" class="field-help">
          {{ t("common.children.maxParty") }}
        </p>
        <p
          v-if="
            children.length &&
            (tariff?.childrenUnderTwoFree ?? tariff?.childrenUnderThreeFree)
          "
          class="child-benefit"
        >
          {{ t("common.children.underTwoFree") }}
        </p>
        <details v-if="children.length" class="child-help">
          <summary>{{ t("common.children.howCalculated") }}</summary>
          <p>{{ t("common.children.hint") }}</p>
          <p>{{ t("common.children.agePolicy") }}</p>
        </details>
      </section>
      <label v-if="!staff"
        >{{ t("public.rate")
        }}<select v-model="form.tariffId" required>
          <option disabled value="">{{ t("public.noActiveRates") }}</option>
          <option
            v-for="offer in quotedTariffs"
            :key="offer.id"
            :value="offer.id"
          >
            {{ offer.name
            }}{{
              offer.priceKind === "discount"
                ? t("public.discountInBookingEditor", [offer.discountPercent])
                : ""
            }}
            {{
              offer.quote
                ? " · " +
                  t("common.pricing.selectedStayTotal", {
                    nights: offer.quote.nights,
                    total: money(offer.quote.total),
                  })
                : ""
            }}
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
            >{{
              t(staff ? "staff.board.roomPriceFor" : "public.roomAndRateFor")
            }}
            {{ form.guests }} {{ t("public.guestsInBookingEditor") }}</small
          >
        </div>
        <strong>{{ displayPrice ? money(displayPrice.total) : "—" }}</strong>
      </div>
      <dl v-if="settlement" class="booking-settlement">
        <div>
          <dt>{{ t("common.settlement.online") }}</dt>
          <dd>{{ money(settlement.onlineAmount) }}</dd>
        </div>
        <div>
          <dt>{{ t("common.settlement.onsite") }}</dt>
          <dd>{{ money(settlement.onsiteAmount) }}</dd>
        </div>
      </dl>
      <p v-else-if="price" class="form-error" role="status">
        {{ t("common.settlement.notConfigured") }}
      </p>
      <details v-if="displayPrice" class="price-breakdown">
        <summary>{{ t("common.pricing.breakdown") }}</summary>
        <dl>
          <div v-for="line in displayPrice.nightlyBreakdown" :key="line.date">
            <dt>
              {{ line.date }} <small>{{ line.periodLabel }}</small>
            </dt>
            <dd>{{ money(line.nightly) }}</dd>
          </div>
        </dl>
        <p class="field-help">{{ t("common.pricing.preview") }}</p>
      </details>
      <details class="booking-conditions">
        <summary>{{ t("common.children.stayConditions") }}</summary>
        <p class="field-help">
          {{ t("public.checkinFrom") }} {{ resort.checkInTime || "14:00" }} ·
          {{ resort.timeZone || "Asia/Almaty"
          }}{{ t("public.refunds100At48HoursOrMore70At2448HoursNone") }}
        </p>
      </details>
      <label class="consent"
        ><input v-model="consent" type="checkbox" required />
        {{
          isDemo
            ? t("public.thisIsADemoBookingWithNoRealCharge")
            : t("common.children.bookingAgreement")
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
        ><button
          class="primary"
          :disabled="
            busy ||
            !price ||
            !settlement ||
            (!staff && !guestAccount.authenticated)
          "
        >
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
<style scoped>
.booking-editor {
  gap: 16px;
  min-width: 0;
}
.booking-editor label {
  font-size: 13px;
  font-weight: 500;
  gap: 6px;
  min-width: 0;
}
.booking-editor input:not([type="checkbox"]),
.booking-editor select {
  font-size: 16px;
  min-height: 44px;
  border-radius: 10px;
  padding: 10px 12px;
  min-width: 0;
}
.booking-editor .form-grid {
  gap: 12px;
}
.booking-editor .booking-property {
  gap: 12px;
}
.booking-editor .booking-property img {
  width: 56px;
  height: 56px;
  border-radius: 12px;
}
.booking-editor .booking-property h3 {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  line-height: 1.3;
  letter-spacing: -0.015em;
}
.booking-editor .booking-property p {
  margin: 3px 0 0;
  font-size: 13px;
}
.booking-editor .field-help,
.booking-editor .form-error {
  margin: 0;
  font-size: 13px;
  line-height: 1.45;
}
.party-section {
  display: grid;
  gap: 12px;
  min-width: 0;
  padding: 14px;
  background: #f5f7f4;
  border-radius: 14px;
}
.party-heading,
.child-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.party-heading h3 {
  margin: 0 0 3px;
  font-size: 15px;
  font-weight: 600;
}
.party-total {
  font-size: 13px;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  color: #405a47;
}
.child-entry {
  display: grid;
  gap: 6px;
  padding-top: 6px;
  border-top: 1px solid #dfe5de;
}
.child-heading label {
  flex: 1;
}
.child-remove {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  flex: 0 0 44px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: #58635b;
  font-size: 24px;
  font-weight: 400;
}
.add-child {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 44px;
  padding: 8px 12px;
  border: 1px solid #d5ded2;
  border-radius: 10px;
  background: #fff;
  color: #35513e;
  font: inherit;
  font-size: 14px;
  font-weight: 500;
}
.child-remove,
.add-child {
  touch-action: manipulation;
  user-select: none;
  -webkit-user-select: none;
  transition:
    background-color 120ms ease-out,
    transform 120ms ease-out;
}
.child-remove:active,
.add-child:active {
  transform: scale(0.98);
  background: #e9eee6;
}
.add-child:disabled {
  opacity: 0.5;
  cursor: default;
}
.child-age {
  display: flex;
  flex-wrap: wrap;
  column-gap: 8px;
  margin: 2px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: #647169;
}
.child-age strong {
  font-weight: 500;
  color: #35513e;
}
.child-benefit {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: #35513e;
}
.child-help,
.booking-conditions {
  color: #617067;
  font-size: 12px;
  line-height: 1.5;
}
.child-help summary,
.booking-conditions summary {
  min-height: 44px;
  align-content: center;
  cursor: pointer;
}
.child-help p {
  margin: 6px 0 0;
}
.booking-editor .quote {
  padding: 14px;
  border-radius: 12px;
  background: #f0f4ed;
  flex-wrap: wrap;
}
.booking-editor .quote span {
  font-size: 14px;
}
.booking-editor .quote small {
  font-size: 12px;
  line-height: 1.5;
  margin-top: 3px;
}
.booking-editor .quote strong {
  font-size: 23px;
  font-weight: 600;
  letter-spacing: -0.025em;
}
.booking-settlement {
  margin: -4px 0 0;
  padding: 0 2px;
  font-size: 13px;
}
.booking-settlement > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 0;
}
.booking-settlement dt {
  color: #617067;
}
.booking-settlement dd {
  margin: 0;
  font-weight: 600;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.booking-editor .price-breakdown {
  margin: 0;
  padding: 0;
  border: 0;
  font-size: 13px;
}
.booking-editor .consent {
  font-size: 13px;
  line-height: 1.5;
  gap: 10px;
  align-items: flex-start;
}
.booking-editor .consent input {
  margin-top: 1px;
}
.booking-editor .form-actions {
  margin-top: 0;
  padding-top: 8px;
}
@media (prefers-reduced-motion: reduce) {
  .child-remove,
  .add-child {
    transition: none;
  }
  .child-remove:active,
  .add-child:active {
    transform: none;
  }
}
</style>
